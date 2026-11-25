"""Tests for scripts/live_local.py: the stream poller and WebSocket server on DynamoDB Local."""

import importlib.util
import json
import time
from pathlib import Path

import pytest
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect as ws_connect

from brainstorm import connections, db, ideas, keys, rooms
from brainstorm.broadcast import ConnectionGoneError

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "live_local.py"
spec = importlib.util.spec_from_file_location("live_local", SCRIPT)
live_local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live_local)

# DynamoDB Local's stream usually has a record within a few hundred milliseconds.
TIMEOUT_S = 10


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    def send(self, connection_id: str, message: bytes) -> None:
        self.sent.append((connection_id, json.loads(message)))

    def close(self, connection_id: str) -> None:
        pass


def poll_until(poller, sender: FakeSender, event_type: str) -> dict:
    """Poll until ``sender`` got an event of ``event_type`` and return it."""
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        poller.poll_once()
        for _, event in sender.sent:
            if event["type"] == event_type:
                return event
        time.sleep(0.1)
    raise AssertionError(f"no {event_type} event; got {sender.sent}")


@pytest.fixture
def endpoint(dynamodb):
    return dynamodb.meta.client.meta.endpoint_url


@pytest.fixture
def room(table):
    return rooms.create_room(table, "prof", "Streams")


def test_poller_broadcasts_a_new_idea(table, endpoint, room):
    connections.connect(table, room["room_id"], "conn-a")
    sender = FakeSender()
    poller = live_local.StreamPoller(table, db.streams_client(endpoint), sender)

    idea = ideas.post_idea(table, room["room_id"], "stu", "Ann", "Use a GSI")

    event = poll_until(poller, sender, "idea_added")
    assert event["room_id"] == room["room_id"]
    assert event["idea"]["idea_id"] == idea["idea_id"]
    assert {cid for cid, _ in sender.sent} == {"conn-a"}


def test_poller_starts_at_the_latest_record(table, endpoint, room):
    connections.connect(table, room["room_id"], "conn-a")
    ideas.post_idea(table, room["room_id"], "stu", "Ann", "Before the poller")
    time.sleep(0.5)
    sender = FakeSender()
    poller = live_local.StreamPoller(table, db.streams_client(endpoint), sender)

    ideas.post_idea(table, room["room_id"], "stu", "Ann", "After the poller")

    poll_until(poller, sender, "idea_added")
    poller.poll_once()
    bodies = [e["idea"]["body"] for _, e in sender.sent if e["type"] == "idea_added"]
    assert bodies == ["After the poller"]


def test_sender_keeps_messages_until_the_socket_opens():
    sender = live_local.LocalSender()
    with pytest.raises(ConnectionGoneError):
        sender.send("unknown", b"{}")

    sender.reserve("c1")
    sender.send("c1", b'{"n": 1}')

    class Conn:
        sent: list[str] = []

        def send(self, message: str) -> None:
            self.sent.append(message)

    conn = Conn()
    assert sender.attach("c1", conn)
    sender.send("c1", b'{"n": 2}')
    assert conn.sent == ['{"n": 1}', '{"n": 2}']


@pytest.fixture
def live(table, endpoint):
    """The WebSocket server and stream poller on a free port, for one test."""
    stack = live_local.LiveStack(table.name, endpoint, port=0).start()
    yield stack
    stack.stop()


def recv_type(sock, event_type: str) -> dict:
    deadline = time.monotonic() + TIMEOUT_S
    while (left := deadline - time.monotonic()) > 0:
        event = json.loads(sock.recv(timeout=left))
        if event["type"] == event_type:
            return event
    raise AssertionError(f"no {event_type} event")


def wait_for_connections(table, room_id: str, count: int, **kwargs) -> list[dict]:
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        listed = connections.list_connections(table, room_id, **kwargs)
        if len(listed) == count:
            return listed
        time.sleep(0.05)
    raise AssertionError(f"expected {count} connections, have {listed}")


def test_two_sockets_see_ideas_votes_and_close(table, live, room):
    rid = room["room_id"]
    url = f"ws://127.0.0.1:{live.port}/?room_id={rid}"
    with ws_connect(url) as a, ws_connect(url) as b:
        assert len(wait_for_connections(table, rid, 2)) == 2

        idea = ideas.post_idea(table, rid, "stu", "Ann", "Use a GSI")
        for sock in (a, b):
            assert recv_type(sock, "idea_added")["idea"]["idea_id"] == idea["idea_id"]

        ideas.vote(table, rid, "stu-2", keys.idea_sk(idea["created_at"], idea["idea_id"]))
        for sock in (a, b):
            assert recv_type(sock, "vote_count_changed")["vote_count"] == 1

        rooms.close_room(table, rid, "prof")
        for sock in (a, b):
            recv_type(sock, "room_closed")
            with pytest.raises(ConnectionClosed):
                sock.recv(timeout=TIMEOUT_S)
    # The broadcaster closes each socket and then deletes its items, so the delete can lag a bit.
    wait_for_connections(table, rid, 0, include_expired=True)


def test_closing_a_socket_deletes_its_connection(table, live, room):
    rid = room["room_id"]
    with ws_connect(f"ws://127.0.0.1:{live.port}/?room_id={rid}"):
        wait_for_connections(table, rid, 1)
    wait_for_connections(table, rid, 0)


@pytest.mark.parametrize("query, status", [("", 400), ("?room_id=nope", 404)])
def test_refuses_bad_rooms(live, query, status):
    with pytest.raises(InvalidStatus) as err:
        ws_connect(f"ws://127.0.0.1:{live.port}/{query}")
    assert err.value.response.status_code == status


def test_refuses_a_closed_room(table, live, room):
    rooms.close_room(table, room["room_id"], "prof")
    with pytest.raises(InvalidStatus) as err:
        ws_connect(f"ws://127.0.0.1:{live.port}/?room_id={room['room_id']}")
    assert err.value.response.status_code == 409
