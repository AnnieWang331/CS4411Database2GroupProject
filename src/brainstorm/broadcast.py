"""Stream Lambda: send each table change to the WebSocket connections of the room it belongs to.

DynamoDB Streams invokes ``lambda_handler`` with a batch of records. Each record becomes an event
(``stream_events.to_event``), events are grouped by room, and each room's connections are listed
once per batch (pattern 21) and sent every event for that room in stream order.

Sending is behind a small ``Sender`` interface so the local stack can reuse ``broadcast`` with its
own WebSocket server; on AWS it's the API Gateway Management API (``ApiGatewaySender``).

- A connection that is gone (``GoneException``) is deleted, as ``$disconnect`` is best effort.
- ``room_closed`` and ``room_expired`` end the board: after sending them, every connection is
  closed and its items deleted, so later changes in the partition don't fan out to stale sockets.
- A record that fails (a send or delete error) is reported in ``batchItemFailures`` and retried by
  Lambda. Retrying resends it to connections that already got it, which clients handle: events
  carry absolute values and clients skip duplicates (docs/api.md, "Messages").
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import boto3
from botocore.exceptions import ClientError

from brainstorm import connections, db
from brainstorm.stream_events import to_event

logger = logging.getLogger(__name__)

# Events after which nothing in the room changes, so its connections are closed and removed.
TERMINAL_EVENTS = {"room_closed", "room_expired"}


class ConnectionGoneError(Exception):
    """The client is no longer connected (it left without a clean ``$disconnect``)."""


class Sender(Protocol):
    """Delivers messages to WebSocket connections; the only part that differs locally and on AWS."""

    def send(self, connection_id: str, message: bytes) -> None:
        """Send one message. Raises ``ConnectionGoneError`` if the client has gone."""

    def close(self, connection_id: str) -> None:
        """Close the connection from the server side. Does nothing if it's already gone."""


class ApiGatewaySender:
    """``Sender`` for an API Gateway WebSocket API, through its Management API."""

    def __init__(self, client) -> None:
        self.client = client

    @classmethod
    def from_endpoint(cls, endpoint_url: str) -> "ApiGatewaySender":
        """Build one for ``https://<api-id>.execute-api.<region>.amazonaws.com/<stage>``."""
        return cls(boto3.client("apigatewaymanagementapi", endpoint_url=endpoint_url))

    def send(self, connection_id: str, message: bytes) -> None:
        try:
            self.client.post_to_connection(ConnectionId=connection_id, Data=message)
        except ClientError as err:
            if _is_gone(err):
                raise ConnectionGoneError(connection_id) from err
            raise

    def close(self, connection_id: str) -> None:
        try:
            self.client.delete_connection(ConnectionId=connection_id)
        except ClientError as err:
            if not _is_gone(err):
                raise


def _is_gone(err: ClientError) -> bool:
    return err.response.get("Error", {}).get("Code") == "GoneException"


@dataclass
class _Pending:
    """An event waiting to be sent, and the stream record (sequence number) it came from."""

    sequence_number: str
    event: dict[str, Any]


@dataclass
class _Room:
    """The batch's events for one room, in stream order."""

    room_id: str
    pending: list[_Pending] = field(default_factory=list)


def broadcast(table, records: list[dict[str, Any]], sender: Sender) -> list[str]:
    """Send the events for a batch of stream records and return the sequence numbers that failed.

    A record whose ``to_event`` raises also fails, so a bad record is logged and retried rather
    than silently dropped.
    """
    failed: list[str] = []
    by_room: dict[str, _Room] = {}
    for record in records:
        sequence_number = record.get("dynamodb", {}).get("SequenceNumber", "")
        try:
            event = to_event(record)
        except Exception:
            logger.exception("couldn't map stream record %s", sequence_number)
            failed.append(sequence_number)
            continue
        if event is None:
            continue
        room = by_room.setdefault(event["room_id"], _Room(event["room_id"]))
        room.pending.append(_Pending(sequence_number, event))

    for room in by_room.values():
        failed.extend(_broadcast_room(table, room, sender))
    return failed


def _broadcast_room(table, room: _Room, sender: Sender) -> list[str]:
    """Send one room's events and return the sequence numbers of the ones that failed."""
    try:
        # Expired connections are included: room_expired only arrives once they've all expired.
        listed = connections.list_connections(table, room.room_id, include_expired=True)
    except Exception:
        logger.exception("couldn't list connections for room %s", room.room_id)
        return [p.sequence_number for p in room.pending]
    connection_ids = [c["connection_id"] for c in listed]

    failed: list[str] = []
    for pending in room.pending:
        message = json.dumps(pending.event).encode()
        ok = True
        still_connected = []
        for connection_id in connection_ids:
            try:
                sender.send(connection_id, message)
                still_connected.append(connection_id)
            except ConnectionGoneError:
                ok &= _remove(table, sender, room.room_id, connection_id, close=False)
            except Exception:
                logger.exception("couldn't send to connection %s", connection_id)
                still_connected.append(connection_id)
                ok = False
        connection_ids = still_connected
        if pending.event["type"] in TERMINAL_EVENTS:
            for connection_id in connection_ids:
                ok &= _remove(table, sender, room.room_id, connection_id, close=True)
            connection_ids = []
        if not ok:
            failed.append(pending.sequence_number)
    return failed


def _remove(table, sender: Sender, room_id: str, connection_id: str, close: bool) -> bool:
    """Close (optionally) and delete a connection; return False if that failed."""
    try:
        if close:
            sender.close(connection_id)
        connections.remove(table, room_id, connection_id)
    except Exception:
        logger.exception("couldn't remove connection %s", connection_id)
        return False
    return True


_table = None
_sender = None


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entry point for the table's stream (with ``ReportBatchItemFailures`` on).

    ``WEBSOCKET_ENDPOINT`` is the WebSocket API's Management API endpoint:
    ``https://<api-id>.execute-api.<region>.amazonaws.com/<stage>``.
    """
    global _table, _sender
    if _table is None:
        _table = db.table()
    if _sender is None:
        _sender = ApiGatewaySender.from_endpoint(os.environ["WEBSOCKET_ENDPOINT"])
    failed = broadcast(_table, event.get("Records", []), _sender)
    return {"batchItemFailures": [{"itemIdentifier": number} for number in failed]}
