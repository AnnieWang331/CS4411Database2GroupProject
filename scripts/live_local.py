"""Live updates on DynamoDB Local: a WebSocket server plus a poller for the table's stream.

Usage: python scripts/live_local.py [--endpoint-url URL] [--table NAME] [--port N]
(``serve_local.py`` starts this too, so you normally don't run it on its own.)

On AWS, API Gateway holds the sockets and Lambda reads the stream. Neither runs locally, so this
script stands in for both, and calls the same code they do:

- ``ws://127.0.0.1:3001/?room_id=<room_id>`` runs ``brainstorm.ws.handle`` for ``$connect`` and
  ``$disconnect``, so connections are stored in the table exactly as on AWS, and a connection to
  a missing or closed room is refused with the same status.
- ``StreamPoller`` reads DynamoDB Local's stream (``describe_stream``, ``get_shard_iterator``,
  ``get_records``) and hands each batch to ``brainstorm.broadcast.broadcast``.

Only the last step, writing to a socket, differs from AWS: ``LocalSender`` writes to this
server's own sockets instead of calling ``post_to_connection``.
"""

import argparse
import logging
import sys
import threading
import time
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from botocore.exceptions import ClientError
from websockets.exceptions import ConnectionClosed
from websockets.sync.server import Server, ServerConnection, serve

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from brainstorm import db, ws  # noqa: E402 - needs the sys.path entry above
from brainstorm.broadcast import ConnectionGoneError, broadcast  # noqa: E402
from brainstorm.stream_events import from_get_records  # noqa: E402

logger = logging.getLogger("live_local")

# Polling an idle shard costs nothing locally; 0.2 s keeps updates about as quick as on AWS.
POLL_INTERVAL_S = 0.2
# How often to look for new shards (DynamoDB rotates them, and a recreated table has new ones).
DESCRIBE_INTERVAL_S = 5.0


class _Client:
    """A socket we accepted. Messages wait in ``backlog`` until the handshake has finished."""

    def __init__(self) -> None:
        self.conn: ServerConnection | None = None
        self.backlog: list[bytes] = []


class LocalSender:
    """``Sender`` that writes to this server's sockets (``post_to_connection`` on AWS).

    A connection is stored in the table during the handshake, before the socket is open, so the
    stream can hand us a message for it first. Those are kept and sent once the socket opens,
    rather than reported as gone (which would make the broadcaster delete the connection).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: dict[str, _Client] = {}

    def reserve(self, connection_id: str) -> None:
        with self._lock:
            self._clients[connection_id] = _Client()

    def attach(self, connection_id: str, conn: ServerConnection) -> bool:
        """Mark the socket open and send what's waiting; False if it was closed meanwhile."""
        with self._lock:
            client = self._clients.get(connection_id)
            if client is None:
                return False
            client.conn = conn
            backlog, client.backlog = client.backlog, []
            try:
                for message in backlog:
                    self._send(connection_id, conn, message)
            except ConnectionGoneError:
                return False
            return True

    def drop(self, connection_id: str) -> None:
        with self._lock:
            self._clients.pop(connection_id, None)

    def send(self, connection_id: str, message: bytes) -> None:
        # Under the lock so a backlog flush and a new message can't swap places.
        with self._lock:
            client = self._clients.get(connection_id)
            if client is None:
                raise ConnectionGoneError(connection_id)
            if client.conn is None:
                client.backlog.append(message)
            else:
                self._send(connection_id, client.conn, message)

    def close(self, connection_id: str) -> None:
        with self._lock:
            client = self._clients.pop(connection_id, None)
        if client is not None and client.conn is not None:
            client.conn.close()

    def _send(self, connection_id: str, conn: ServerConnection, message: bytes) -> None:
        try:
            # Text frames, like API Gateway sends for post_to_connection.
            conn.send(message.decode())
        except ConnectionClosed as err:
            self._clients.pop(connection_id, None)
            raise ConnectionGoneError(connection_id) from err


def _ws_event(route_key: str, connection_id: str, query: dict[str, str] | None = None) -> dict:
    """The parts of an API Gateway WebSocket event that ``ws.handle`` reads."""
    return {
        "requestContext": {"routeKey": route_key, "connectionId": connection_id},
        "queryStringParameters": query or None,
    }


def make_server(table, sender: LocalSender, host: str = "127.0.0.1", port: int = 3001) -> Server:
    """Return a WebSocket server that runs ``$connect``/``$disconnect`` like API Gateway.

    ``table`` is only used by the handshake and disconnect threads, which take turns on it (boto3
    resources aren't thread-safe).
    """
    table_lock = threading.Lock()

    def process_request(conn: ServerConnection, request) -> Any:
        connection_id = conn.id.hex[:16]
        query = dict(parse_qsl(urlsplit(request.path).query))
        sender.reserve(connection_id)
        with table_lock:
            status = ws.handle(table, _ws_event("$connect", connection_id, query))["statusCode"]
        if status != 200:
            sender.drop(connection_id)
            return conn.respond(HTTPStatus(status), f"{HTTPStatus(status).phrase}\n")
        return None

    def handler(conn: ServerConnection) -> None:
        connection_id = conn.id.hex[:16]
        try:
            if sender.attach(connection_id, conn):
                for _ in conn:  # $default: ignore anything the client sends
                    pass
        except ConnectionClosed:
            pass
        finally:
            sender.drop(connection_id)
            with table_lock:
                ws.handle(table, _ws_event("$disconnect", connection_id))

    return serve(handler, host, port, process_request=process_request)


class StreamPoller:
    """Read the table's stream and broadcast each batch, like the stream Lambda's trigger.

    Shards that already exist when it starts are read from ``LATEST`` (only changes from now on);
    shards that appear later are read from ``TRIM_HORIZON`` so nothing in them is missed.

    Lambda retries a failed record; here a failure is only logged. Locally a send fails only when
    a socket closes mid-send, and that connection is gone anyway.
    """

    def __init__(self, table, streams, sender, stream_arn: str | None = None) -> None:
        self.table = table
        self.streams = streams
        self.sender = sender
        self.stream_arn = stream_arn or table.latest_stream_arn
        if not self.stream_arn:
            raise RuntimeError(f"table {table.name} has no stream (run create_table.py)")
        self._iterators: dict[str, str | None] = {}  # shard id -> iterator (None: finished)
        self._last_seq: dict[str, str] = {}
        self._last_describe = 0.0
        self._stop = threading.Event()
        self._refresh_shards(initial=True)

    def _list_shards(self) -> list[dict[str, Any]]:
        shards, start_after = [], None
        while True:
            kwargs = {"StreamArn": self.stream_arn}
            if start_after:
                kwargs["ExclusiveStartShardId"] = start_after
            desc = self.streams.describe_stream(**kwargs)["StreamDescription"]
            shards.extend(desc["Shards"])
            start_after = desc.get("LastEvaluatedShardId")
            if not start_after:
                return shards

    def _iterator(self, shard_id: str, kind: str, **kwargs) -> str:
        return self.streams.get_shard_iterator(
            StreamArn=self.stream_arn, ShardId=shard_id, ShardIteratorType=kind, **kwargs
        )["ShardIterator"]

    def _refresh_shards(self, initial: bool = False) -> None:
        self._last_describe = time.monotonic()
        for shard in self._list_shards():
            shard_id = shard["ShardId"]
            if shard_id in self._iterators:
                continue
            closed = "EndingSequenceNumber" in shard["SequenceNumberRange"]
            if initial and closed:
                self._iterators[shard_id] = None  # its changes are all from before we started
            else:
                self._iterators[shard_id] = self._iterator(
                    shard_id, "LATEST" if initial else "TRIM_HORIZON"
                )

    def poll_once(self) -> int:
        """Read every shard once, broadcast what came back and return the number of records."""
        if time.monotonic() - self._last_describe >= DESCRIBE_INTERVAL_S:
            self._refresh_shards()
        total = 0
        for shard_id, iterator in list(self._iterators.items()):
            if iterator is None:
                continue
            try:
                page = self.streams.get_records(ShardIterator=iterator, Limit=1000)
            except ClientError as err:
                if err.response["Error"]["Code"] != "ExpiredIteratorException":
                    raise
                page = self._resume(shard_id)
            records = page["Records"]
            # No next iterator means the shard is closed and fully read.
            self._iterators[shard_id] = page.get("NextShardIterator")
            if not records:
                continue
            self._last_seq[shard_id] = records[-1]["dynamodb"]["SequenceNumber"]
            total += len(records)
            failed = broadcast(self.table, [from_get_records(r) for r in records], self.sender)
            if failed:
                logger.warning("couldn't send %d of %d records", len(failed), len(records))
        return total

    def _resume(self, shard_id: str) -> dict[str, Any]:
        """Get a fresh iterator for a shard whose iterator expired (15 minutes unused)."""
        if shard_id in self._last_seq:
            seq = self._last_seq[shard_id]
            iterator = self._iterator(shard_id, "AFTER_SEQUENCE_NUMBER", SequenceNumber=seq)
        else:
            iterator = self._iterator(shard_id, "LATEST")
        return self.streams.get_records(ShardIterator=iterator, Limit=1000)

    def run(self) -> None:
        """Poll until ``stop`` is called; errors are logged and polling carries on."""
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:
                logger.exception("stream poll failed")
                self._stop.wait(1.0)
            self._stop.wait(POLL_INTERVAL_S)

    def stop(self) -> None:
        self._stop.set()


class LiveStack:
    """The WebSocket server and stream poller, each on a background thread."""

    def __init__(self, table_name: str, endpoint_url: str | None, port: int = 3001) -> None:
        # Separate resources for the poller and the server: boto3 resources aren't thread-safe.
        self.sender = LocalSender()
        self.server = make_server(db.table(table_name, endpoint_url), self.sender, port=port)
        self.poller = StreamPoller(
            db.table(table_name, endpoint_url), db.streams_client(endpoint_url), self.sender
        )
        self._threads = [
            threading.Thread(target=self.server.serve_forever, name="ws-server", daemon=True),
            threading.Thread(target=self.poller.run, name="stream-poller", daemon=True),
        ]

    @property
    def port(self) -> int:
        return self.server.socket.getsockname()[1]

    def start(self) -> "LiveStack":
        for thread in self._threads:
            thread.start()
        return self

    def stop(self) -> None:
        self.poller.stop()
        self.server.shutdown()
        for thread in self._threads:
            thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint-url", default=db.endpoint_url(), help="e.g. localhost:8000")
    parser.add_argument("--table", default=db.table_name(), help="table name")
    parser.add_argument("--port", type=int, default=3001, help="WebSocket port")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    stack = LiveStack(args.table, args.endpoint_url, args.port).start()
    print(f"Live updates on ws://127.0.0.1:{stack.port}/?room_id=<room_id> (Ctrl+C to stop)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        stack.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
