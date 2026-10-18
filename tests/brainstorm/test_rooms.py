"""Tests for room operations against DynamoDB Local."""

from datetime import timedelta

import pytest

from brainstorm import keys, rooms
from brainstorm.errors import (
    CodeUnavailableError,
    InvalidInputError,
    NotRoomOwnerError,
    RoomClosedError,
    RoomNotFoundError,
)


def test_create_room_writes_meta_and_code(table):
    room = rooms.create_room(table, "prof", "Indexing strategies")
    assert room["status"] == "open"
    assert rooms.get_room(table, room["room_id"])["topic"] == "Indexing strategies"
    assert rooms.resolve_code(table, room["code"].lower())["room_id"] == room["room_id"]


def test_create_room_rejects_empty_topic(table):
    with pytest.raises(InvalidInputError):
        rooms.create_room(table, "prof", "   ")


def test_create_room_retries_taken_code(table, monkeypatch):
    taken = rooms.create_room(table, "prof", "First")["code"]
    codes = iter([taken, taken, "FRESH2"])
    monkeypatch.setattr(keys, "new_code", lambda: next(codes))
    assert rooms.create_room(table, "prof", "Second")["code"] == "FRESH2"


def test_create_room_gives_up_when_codes_exhausted(table, monkeypatch):
    taken = rooms.create_room(table, "prof", "First")["code"]
    monkeypatch.setattr(keys, "new_code", lambda: taken)
    with pytest.raises(CodeUnavailableError):
        rooms.create_room(table, "prof", "Second")


def test_expired_code_can_be_reused(table, monkeypatch):
    old = rooms.create_room(table, "prof", "Old", ttl=timedelta(seconds=-10))
    monkeypatch.setattr(keys, "new_code", lambda: old["code"])
    new = rooms.create_room(table, "prof", "New")
    assert rooms.resolve_code(table, old["code"])["room_id"] == new["room_id"]


def test_expired_room_is_not_found(table):
    room = rooms.create_room(table, "prof", "Gone", ttl=timedelta(seconds=-10))
    with pytest.raises(RoomNotFoundError):
        rooms.get_room(table, room["room_id"])
    with pytest.raises(RoomNotFoundError):
        rooms.resolve_code(table, room["code"])


def test_unknown_code_is_not_found(table):
    with pytest.raises(RoomNotFoundError):
        rooms.resolve_code(table, "ZZZZZZ")


def test_join_is_idempotent_and_keeps_joined_at(table):
    room = rooms.create_room(table, "prof", "Topic")
    first = rooms.join_room(table, room["room_id"], "stu-1", "Roah")
    again = rooms.join_room(table, room["room_id"], "stu-1", "Roah C.")
    assert again["joined_at"] == first["joined_at"]
    assert again["display_name"] == "Roah C."
    assert again["expires_at"] == room["expires_at"]
    rooms.join_room(table, room["room_id"], "stu-2", "Sachin")
    names = {p["display_name"] for p in rooms.list_participants(table, room["room_id"])}
    assert names == {"Roah C.", "Sachin"}


def test_close_room_blocks_joins_and_frees_code(table):
    room = rooms.create_room(table, "prof", "Topic")
    rooms.close_room(table, room["room_id"], "prof")
    assert rooms.get_room(table, room["room_id"])["status"] == "closed"
    with pytest.raises(RoomNotFoundError):
        rooms.resolve_code(table, room["code"])
    with pytest.raises(RoomClosedError):
        rooms.join_room(table, room["room_id"], "stu-1", "Roah")


def test_close_room_checks_owner_and_status(table):
    room = rooms.create_room(table, "prof", "Topic")
    with pytest.raises(NotRoomOwnerError):
        rooms.close_room(table, room["room_id"], "someone-else")
    rooms.close_room(table, room["room_id"], "prof")
    with pytest.raises(RoomClosedError):
        rooms.close_room(table, room["room_id"], "prof")


def test_close_expired_room_is_not_found(table):
    room = rooms.create_room(table, "prof", "Gone", ttl=timedelta(seconds=-10))
    with pytest.raises(RoomNotFoundError):
        rooms.close_room(table, room["room_id"], "prof")


def test_list_owner_rooms_newest_first_and_live_only(table):
    first = rooms.create_room(table, "prof", "First")
    second = rooms.create_room(table, "prof", "Second")
    rooms.create_room(table, "prof", "Expired", ttl=timedelta(seconds=-10))
    rooms.create_room(table, "other", "Not mine")
    listed = [r["room_id"] for r in rooms.list_owner_rooms(table, "prof")]
    assert listed == [second["room_id"], first["room_id"]]
