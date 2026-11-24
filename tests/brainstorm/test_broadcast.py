"""Tests for the stream broadcaster: real connections on DynamoDB Local, a fake sender."""

import json
from datetime import timedelta
from typing import Any

import boto3
import pytest
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from brainstorm import broadcast, connections, ideas, keys, rooms
from brainstorm.broadcast import ApiGatewaySender, ConnectionGoneError

_serializer = TypeSerializer()
TTL_IDENTITY = {"type": "Service", "principalId": "dynamodb.amazonaws.com"}


class FakeSender:
    """Records what was sent; ``gone`` ids raise ConnectionGoneError, ``broken`` ids fail."""

    def __init__(self, gone=(), broken=()) -> None:
        self.gone = set(gone)
        self.broken = set(broken)
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.closed: list[str] = []

    def send(self, connection_id: str, message: bytes) -> None:
        if connection_id in self.gone:
            raise ConnectionGoneError(connection_id)
        if connection_id in self.broken:
            raise RuntimeError("send failed")
        self.sent.append((connection_id, json.loads(message)))

    def close(self, connection_id: str) -> None:
        self.closed.append(connection_id)

    def types_for(self, connection_id: str) -> list[str]:
        return [event["type"] for cid, event in self.sent if cid == connection_id]


_sequence = iter(range(1, 10_000))


def record(name: str, new: dict | None = None, old: dict | None = None, identity=None) -> dict:
    """Build a NEW_AND_OLD_IMAGES stream record (DynamoDB JSON) with a fresh sequence number."""
    images = {}
    for key, image in (("NewImage", new), ("OldImage", old)):
        if image is not None:
            images[key] = {k: _serializer.serialize(v) for k, v in image.items()}
    out = {
        "eventName": name,
        "dynamodb": {"SequenceNumber": str(next(_sequence)), **images},
    }
    if identity is not None:
        out["userIdentity"] = identity
    return out


def get(table, pk: str, sk: str) -> dict:
    return table.get_item(Key={"PK": pk, "SK": sk})["Item"]


def ws_items(table, room_id: str) -> list[dict]:
    return connections.list_connections(table, room_id, include_expired=True)


def idea_insert(table, room_id: str, user: str = "stu") -> dict:
    idea = ideas.post_idea(table, room_id, user, "Name", "An idea")
    return record("INSERT", new=get(table, keys.room_pk(room_id), idea["SK"]))


def close_record(table, room_id: str) -> dict:
    old = get(table, keys.room_pk(room_id), keys.META)
    rooms.close_room(table, room_id, "prof")
    return record("MODIFY", new=get(table, keys.room_pk(room_id), keys.META), old=old)


@pytest.fixture
def room(table):
    return rooms.create_room(table, "prof", "Topic")


def test_event_goes_to_every_connection_in_the_room(table, room):
    other = rooms.create_room(table, "prof", "Other")
    for cid in ("c1", "c2"):
        connections.connect(table, room["room_id"], cid)
    connections.connect(table, other["room_id"], "elsewhere")
    sender = FakeSender()
    assert broadcast.broadcast(table, [idea_insert(table, room["room_id"])], sender) == []
    assert sorted(cid for cid, _ in sender.sent) == ["c1", "c2"]
    assert all(event["type"] == "idea_added" for _, event in sender.sent)
    assert all("PK" not in event["idea"] for _, event in sender.sent)


def test_records_without_an_event_send_nothing(table, room):
    connections.connect(table, room["room_id"], "c1")
    code = get(table, keys.code_pk(room["code"]), keys.META)
    sender = FakeSender()
    assert broadcast.broadcast(table, [record("INSERT", new=code)], sender) == []
    assert sender.sent == []


def test_one_connections_query_per_room_per_batch(table, room, monkeypatch):
    connections.connect(table, room["room_id"], "c1")
    batch = [idea_insert(table, room["room_id"]) for _ in range(3)]
    calls = []
    real = connections.list_connections

    def counting(table, room_id, **kwargs):
        calls.append(room_id)
        return real(table, room_id, **kwargs)

    monkeypatch.setattr(connections, "list_connections", counting)
    sender = FakeSender()
    assert broadcast.broadcast(table, batch, sender) == []
    assert calls == [room["room_id"]]
    assert sender.types_for("c1") == ["idea_added"] * 3


def test_gone_connection_is_deleted_and_not_sent_again(table, room):
    connections.connect(table, room["room_id"], "c1")
    connections.connect(table, room["room_id"], "gone")
    batch = [idea_insert(table, room["room_id"]) for _ in range(2)]
    sender = FakeSender(gone={"gone"})
    assert broadcast.broadcast(table, batch, sender) == []
    assert [c["connection_id"] for c in ws_items(table, room["room_id"])] == ["c1"]
    assert "Item" not in table.get_item(Key={"PK": keys.connection_pk("gone"), "SK": keys.META})
    assert sender.types_for("c1") == ["idea_added", "idea_added"]


def test_close_sends_room_closed_then_removes_every_connection(table, room):
    room_id = room["room_id"]
    for cid in ("c1", "c2"):
        connections.connect(table, room_id, cid)
    sender = FakeSender()
    assert broadcast.broadcast(table, [close_record(table, room_id)], sender) == []
    assert sender.types_for("c1") == ["room_closed"]
    assert sender.types_for("c2") == ["room_closed"]
    assert sorted(sender.closed) == ["c1", "c2"]
    assert ws_items(table, room_id) == []
    for cid in ("c1", "c2"):
        assert "Item" not in table.get_item(Key={"PK": keys.connection_pk(cid), "SK": keys.META})


def test_nothing_is_sent_to_a_closed_rooms_old_connections(table, room):
    room_id = room["room_id"]
    connections.connect(table, room_id, "c1")
    later = idea_insert(table, room_id)  # posted before the close, delivered after it
    sender = FakeSender()
    assert broadcast.broadcast(table, [close_record(table, room_id), later], sender) == []
    assert sender.types_for("c1") == ["room_closed"]
    sender = FakeSender()
    assert broadcast.broadcast(table, [later], sender) == []  # a later batch
    assert sender.sent == []


def test_room_expired_reaches_connections_past_their_ttl(table):
    room = rooms.create_room(table, "prof", "Soon gone", ttl=timedelta(seconds=30))
    room_id = room["room_id"]
    connections.connect(table, room_id, "c1")
    meta = get(table, keys.room_pk(room_id), keys.META)
    # By the time TTL deletes the room, its connections have expired too.
    table.update_item(
        Key={"PK": keys.room_pk(room_id), "SK": keys.connection_sk("c1")},
        UpdateExpression="SET expires_at = :past",
        ExpressionAttributeValues={":past": keys.epoch(keys.utc_now()) - 10},
    )
    sender = FakeSender()
    batch = [record("REMOVE", old=meta, identity=TTL_IDENTITY)]
    assert broadcast.broadcast(table, batch, sender) == []
    assert sender.types_for("c1") == ["room_expired"]
    assert sender.closed == ["c1"]
    assert ws_items(table, room_id) == []


def test_failed_send_reports_only_that_record(table, room):
    room_id = room["room_id"]
    other = rooms.create_room(table, "prof", "Other")
    connections.connect(table, room_id, "broken")
    connections.connect(table, other["room_id"], "fine")
    bad = idea_insert(table, room_id)
    good = idea_insert(table, other["room_id"])
    sender = FakeSender(broken={"broken"})
    assert broadcast.broadcast(table, [bad, good], sender) == [bad["dynamodb"]["SequenceNumber"]]
    assert sender.types_for("fine") == ["idea_added"]
    # The broken connection is kept: it isn't known to be gone, so a retry can reach it.
    assert [c["connection_id"] for c in ws_items(table, room_id)] == ["broken"]


def test_failed_connections_query_fails_that_rooms_records(table, room, monkeypatch):
    connections.connect(table, room["room_id"], "c1")
    batch = [idea_insert(table, room["room_id"]) for _ in range(2)]

    def fail(*args, **kwargs):
        raise ClientError({"Error": {"Code": "ThrottlingException"}}, "Query")

    monkeypatch.setattr(connections, "list_connections", fail)
    failed = broadcast.broadcast(table, batch, FakeSender())
    assert failed == [r["dynamodb"]["SequenceNumber"] for r in batch]


def test_unmappable_record_fails_instead_of_being_dropped(table):
    # A vote-count change without the idea's id: to_event raises KeyError.
    idea = {"PK": "ROOM#r1", "SK": "IDEA#x", "entity_type": "IDEA"}
    bad = record("MODIFY", new=idea | {"vote_count": 1}, old=idea | {"vote_count": 0})
    assert broadcast.broadcast(table, [bad], FakeSender()) == [bad["dynamodb"]["SequenceNumber"]]


def test_lambda_handler_reports_batch_item_failures(table, room, monkeypatch):
    connections.connect(table, room["room_id"], "broken")
    bad = idea_insert(table, room["room_id"])
    monkeypatch.setattr(broadcast, "_table", table)
    monkeypatch.setattr(broadcast, "_sender", FakeSender(broken={"broken"}))
    result = broadcast.lambda_handler({"Records": [bad]}, None)
    assert result == {"batchItemFailures": [{"itemIdentifier": bad["dynamodb"]["SequenceNumber"]}]}


# ApiGatewaySender against a stubbed Management API (no AWS calls).


@pytest.fixture
def stubbed():
    client = boto3.client(
        "apigatewaymanagementapi",
        endpoint_url="https://example.execute-api.us-east-1.amazonaws.com/prod",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    with Stubber(client) as stubber:
        yield ApiGatewaySender(client), stubber
        stubber.assert_no_pending_responses()


def test_api_gateway_sender_posts_to_connection(stubbed):
    sender, stubber = stubbed
    stubber.add_response("post_to_connection", {}, {"ConnectionId": "c1", "Data": b"{}"})
    sender.send("c1", b"{}")


def test_api_gateway_sender_turns_gone_into_connection_gone(stubbed):
    sender, stubber = stubbed
    stubber.add_client_error("post_to_connection", "GoneException", http_status_code=410)
    with pytest.raises(ConnectionGoneError):
        sender.send("c1", b"{}")


def test_api_gateway_sender_raises_other_errors(stubbed):
    sender, stubber = stubbed
    stubber.add_client_error("post_to_connection", "LimitExceededException", http_status_code=429)
    with pytest.raises(ClientError):
        sender.send("c1", b"{}")


def test_api_gateway_sender_close_ignores_gone(stubbed):
    sender, stubber = stubbed
    stubber.add_response("delete_connection", {}, {"ConnectionId": "c1"})
    stubber.add_client_error("delete_connection", "GoneException", http_status_code=410)
    sender.close("c1")
    sender.close("c1")
