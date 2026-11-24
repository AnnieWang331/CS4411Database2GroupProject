"""Tests for WebSocket connections (data layer and handler) against DynamoDB Local."""

from datetime import timedelta

import pytest
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from brainstorm import connections, ideas, keys, rooms, ws
from brainstorm.errors import InvalidInputError, RoomClosedError, RoomNotFoundError


def ws_event(route_key: str, connection_id: str, query: dict | None = None) -> dict:
    """Build the parts of an API Gateway WebSocket event that ws.handle reads."""
    return {
        "requestContext": {"routeKey": route_key, "connectionId": connection_id},
        "queryStringParameters": query,
    }


def test_connect_stores_connection_with_room_ttl(table):
    room = rooms.create_room(table, "prof", "Topic")
    conn = connections.connect(table, room["room_id"], "abc123=")
    assert conn["expires_at"] == room["expires_at"]
    listed = connections.list_connections(table, room["room_id"])
    assert [c["connection_id"] for c in listed] == ["abc123="]
    lookup = table.get_item(Key={"PK": keys.connection_pk("abc123="), "SK": keys.META})["Item"]
    assert lookup["room_id"] == room["room_id"]
    assert lookup["expires_at"] == room["expires_at"]


def test_disconnect_removes_both_items(table):
    room = rooms.create_room(table, "prof", "Topic")
    connections.connect(table, room["room_id"], "c1")
    connections.connect(table, room["room_id"], "c2")
    assert connections.disconnect(table, "c1") == room["room_id"]
    assert [c["connection_id"] for c in connections.list_connections(table, room["room_id"])] == [
        "c2"
    ]
    assert "Item" not in table.get_item(Key={"PK": keys.connection_pk("c1"), "SK": keys.META})


def test_disconnect_unknown_connection_is_a_no_op(table):
    assert connections.disconnect(table, "never-connected") is None


def test_disconnect_works_after_room_closes(table):
    room = rooms.create_room(table, "prof", "Topic")
    connections.connect(table, room["room_id"], "c1")
    rooms.close_room(table, room["room_id"], "prof")
    assert connections.disconnect(table, "c1") == room["room_id"]
    assert connections.list_connections(table, room["room_id"]) == []


def test_connect_to_missing_or_expired_room_is_not_found(table):
    with pytest.raises(RoomNotFoundError):
        connections.connect(table, "no-such-room", "c1")
    expired = rooms.create_room(table, "prof", "Gone", ttl=timedelta(seconds=-10))
    with pytest.raises(RoomNotFoundError):
        connections.connect(table, expired["room_id"], "c1")
    # Nothing half-written for the disconnect to trip over.
    assert connections.disconnect(table, "c1") is None


def test_connect_to_closed_room_is_refused(table):
    room = rooms.create_room(table, "prof", "Topic")
    rooms.close_room(table, room["room_id"], "prof")
    with pytest.raises(RoomClosedError):
        connections.connect(table, room["room_id"], "c1")


def test_connection_id_cannot_contain_hash(table):
    room = rooms.create_room(table, "prof", "Topic")
    with pytest.raises(InvalidInputError):
        connections.connect(table, room["room_id"], "bad#id")


def test_board_load_never_reads_connections(table):
    room = rooms.create_room(table, "prof", "Topic")
    idea = ideas.post_idea(table, room["room_id"], "stu-1", "Roah", "An idea")
    ideas.add_comment(table, room["room_id"], idea["SK"], "stu-2", "Sachin", "A comment")
    connections.connect(table, room["room_id"], "c1")
    board = ideas.load_board(table, room["room_id"], include_comments=True)
    assert len(board["ideas"]) == 1
    # load_board also filters by entity_type, so check the raw key range itself: SK <= META (P8)
    # is the widest board query, and WS# sorts after it.
    raw = rooms.query_all(
        table,
        KeyConditionExpression=Key("PK").eq(keys.room_pk(room["room_id"]))
        & Key("SK").lte(keys.META),
    )
    assert {item["entity_type"] for item in raw} == {"ROOM", "IDEA", "COMMENT"}


def test_ws_handler_connect_disconnect_and_default(table):
    room = rooms.create_room(table, "prof", "Topic")
    room_id = room["room_id"]
    assert ws.handle(table, ws_event("$connect", "c1", {"room_id": room_id})) == {"statusCode": 200}
    assert len(connections.list_connections(table, room_id)) == 1
    assert ws.handle(table, ws_event("$default", "c1")) == {"statusCode": 200}
    assert ws.handle(table, ws_event("$disconnect", "c1")) == {"statusCode": 200}
    assert connections.list_connections(table, room_id) == []


def test_ws_handler_refuses_bad_connects(table):
    room = rooms.create_room(table, "prof", "Topic")
    assert ws.handle(table, ws_event("$connect", "c1"))["statusCode"] == 400
    assert ws.handle(table, ws_event("$connect", "c1", {"room_id": "nope"}))["statusCode"] == 404
    rooms.close_room(table, room["room_id"], "prof")
    closed = ws_event("$connect", "c1", {"room_id": room["room_id"]})
    assert ws.handle(table, closed)["statusCode"] == 409


def test_connect_rejects_bad_room_ids(table):
    for room_id in ["x" * 3000, "a#b"]:
        with pytest.raises(InvalidInputError):
            connections.connect(table, room_id, "c1")
        status = ws.handle(table, ws_event("$connect", "c1", {"room_id": room_id}))["statusCode"]
        assert status == 400


def test_connect_undoes_itself_if_room_closes_during_connect(table, monkeypatch):
    room = rooms.create_room(table, "prof", "Topic")
    room_id = room["room_id"]
    real_write = connections.transact_write

    def close_then_write(table, items):
        # The close commits between connect's first read and its write.
        rooms.close_room(table, room_id, "prof")
        monkeypatch.setattr(connections, "transact_write", real_write)
        real_write(table, items)

    monkeypatch.setattr(connections, "transact_write", close_then_write)
    with pytest.raises(RoomClosedError):
        connections.connect(table, room_id, "c1")
    assert connections.list_connections(table, room_id) == []
    assert connections.disconnect(table, "c1") is None


def throttled() -> ClientError:
    return ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "GetItem")


def test_connect_undoes_itself_if_second_read_fails(table, monkeypatch):
    room = rooms.create_room(table, "prof", "Topic")
    room_id = room["room_id"]
    reads = []

    def get_room_then_throttle(table, room_id, consistent=False):
        reads.append(room_id)
        if len(reads) == 2:
            raise throttled()
        return rooms.get_room(table, room_id, consistent=consistent)

    monkeypatch.setattr(connections, "get_room", get_room_then_throttle)
    status = ws.handle(table, ws_event("$connect", "c1", {"room_id": room_id}))["statusCode"]
    assert status == 503
    assert connections.list_connections(table, room_id) == []
    assert connections.disconnect(table, "c1") is None


def test_failed_undo_keeps_the_original_error(table, monkeypatch):
    room = rooms.create_room(table, "prof", "Topic")
    room_id = room["room_id"]
    real_write = connections.transact_write

    def close_then_write(table, items):
        rooms.close_room(table, room_id, "prof")
        monkeypatch.setattr(connections, "remove", fail_delete)
        real_write(table, items)

    def fail_delete(table, room_id, connection_id):
        raise throttled()

    monkeypatch.setattr(connections, "transact_write", close_then_write)
    with pytest.raises(RoomClosedError):
        connections.connect(table, room_id, "c1")
