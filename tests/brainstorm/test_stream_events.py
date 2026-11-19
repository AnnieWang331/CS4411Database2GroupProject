"""Tests for mapping DynamoDB Streams records to live-update events (no DynamoDB needed)."""

from typing import Any

from boto3.dynamodb.types import TypeSerializer

from brainstorm import keys
from brainstorm.stream_events import to_event

ROOM_ID = "01JAB3K9"
PK = keys.room_pk(ROOM_ID)
TS = "2026-10-18T14:05:31.120Z"
EXPIRES = 1761055200
IDEA_SK = keys.idea_sk(TS, "01JAB4QX")
TTL_IDENTITY = {"type": "Service", "principalId": "dynamodb.amazonaws.com"}
HIDDEN = {"PK", "SK", "GSI1PK", "GSI1SK", "owner_id"}

_serializer = TypeSerializer()


def record(
    name: str,
    new: dict[str, Any] | None = None,
    old: dict[str, Any] | None = None,
    identity: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a NEW_AND_OLD_IMAGES stream record with images in DynamoDB JSON."""
    images = {}
    for key, image in (("NewImage", new), ("OldImage", old)):
        if image is not None:
            images[key] = {k: _serializer.serialize(v) for k, v in image.items()}
    item = new or old
    out = {
        "eventName": name,
        "dynamodb": {
            "Keys": {k: _serializer.serialize(item[k]) for k in ("PK", "SK")},
            "StreamViewType": "NEW_AND_OLD_IMAGES",
            **images,
        },
    }
    if identity is not None:
        out["userIdentity"] = identity
    return out


def room(**changes: Any) -> dict[str, Any]:
    item = {
        "PK": PK,
        "SK": keys.META,
        "entity_type": "ROOM",
        "GSI1PK": keys.user_key("prof-lee"),
        "GSI1SK": keys.owner_room_sk(TS, ROOM_ID),
        "room_id": ROOM_ID,
        "code": "K7QM4X",
        "topic": "Indexing strategies",
        "status": "open",
        "owner_id": "prof-lee",
        "created_at": TS,
        "expires_at": EXPIRES,
    }
    return item | changes


def idea(**changes: Any) -> dict[str, Any]:
    item = {
        "PK": PK,
        "SK": IDEA_SK,
        "entity_type": "IDEA",
        "idea_id": "01JAB4QX",
        "author_id": "stu-042",
        "author_name": "Roah",
        "body": "Use a GSI for top-voted ideas",
        "vote_count": 0,
        "comment_count": 0,
        "created_at": TS,
        "expires_at": EXPIRES,
    }
    return item | changes


def comment() -> dict[str, Any]:
    return {
        "PK": PK,
        "SK": keys.comment_sk("01JAB4QX", TS, "01JAB5A1"),
        "entity_type": "COMMENT",
        "comment_id": "01JAB5A1",
        "idea_id": "01JAB4QX",
        "author_id": "stu-007",
        "author_name": "Sachin",
        "body": "Client-side sort is enough",
        "created_at": TS,
        "expires_at": EXPIRES,
    }


def participant(**changes: Any) -> dict[str, Any]:
    item = {
        "PK": PK,
        "SK": keys.user_key("stu-042"),
        "entity_type": "PARTICIPANT",
        "user_id": "stu-042",
        "display_name": "Roah",
        "joined_at": TS,
        "expires_at": EXPIRES,
    }
    return item | changes


def vote() -> dict[str, Any]:
    return {
        "PK": PK,
        "SK": keys.vote_sk("stu-007", "01JAB4QX"),
        "entity_type": "VOTE",
        "user_id": "stu-007",
        "idea_id": "01JAB4QX",
        "idea_sk": IDEA_SK,
        "created_at": TS,
        "expires_at": EXPIRES,
    }


def connection() -> dict[str, Any]:
    return {
        "PK": PK,
        "SK": keys.connection_sk("Lx3fGc7NoAMCJ4w="),
        "entity_type": "CONNECTION",
        "connection_id": "Lx3fGc7NoAMCJ4w=",
        "room_id": ROOM_ID,
        "connected_at": TS,
        "expires_at": EXPIRES,
    }


def connection_lookup() -> dict[str, Any]:
    return connection() | {
        "PK": keys.connection_pk("Lx3fGc7NoAMCJ4w="),
        "SK": keys.META,
        "entity_type": "CONNECTION_LOOKUP",
    }


def code() -> dict[str, Any]:
    return {
        "PK": keys.code_pk("K7QM4X"),
        "SK": keys.META,
        "entity_type": "ROOM_CODE",
        "code": "K7QM4X",
        "room_id": ROOM_ID,
        "created_at": TS,
        "expires_at": EXPIRES,
    }


def assert_no_hidden(value: Any) -> None:
    if isinstance(value, dict):
        assert not HIDDEN & value.keys()
        for v in value.values():
            assert_no_hidden(v)


def test_idea_insert_is_idea_added():
    event = to_event(record("INSERT", new=idea()))
    expected = {k: v for k, v in idea().items() if k not in HIDDEN} | {"idea_sk": IDEA_SK}
    assert event == {"type": "idea_added", "room_id": ROOM_ID, "idea": expected}
    assert_no_hidden(event)


def test_vote_count_change_is_vote_count_changed():
    event = to_event(record("MODIFY", new=idea(vote_count=3), old=idea(vote_count=2)))
    assert event == {
        "type": "vote_count_changed",
        "room_id": ROOM_ID,
        "idea_id": "01JAB4QX",
        "idea_sk": IDEA_SK,
        "vote_count": 3,
    }
    assert type(event["vote_count"]) is int


def test_vote_count_drop_to_zero_is_sent():
    event = to_event(record("MODIFY", new=idea(vote_count=0), old=idea(vote_count=1)))
    assert event["type"] == "vote_count_changed"
    assert event["vote_count"] == 0


def test_comment_insert_is_comment_added():
    event = to_event(record("INSERT", new=comment()))
    expected = {k: v for k, v in comment().items() if k not in HIDDEN}
    assert event == {"type": "comment_added", "room_id": ROOM_ID, "comment": expected}


def test_participant_insert_is_participant_joined():
    event = to_event(record("INSERT", new=participant()))
    expected = {k: v for k, v in participant().items() if k not in HIDDEN}
    assert event == {"type": "participant_joined", "room_id": ROOM_ID, "participant": expected}


def test_room_close_with_closed_at_is_room_closed():
    # The exact write close_room makes: status open -> closed and closed_at set together.
    closed_at = "2026-10-18T15:00:00.000Z"
    event = to_event(record("MODIFY", new=room(status="closed", closed_at=closed_at), old=room()))
    assert event == {"type": "room_closed", "room_id": ROOM_ID, "closed_at": closed_at}
    assert_no_hidden(event)


def test_room_ttl_delete_is_room_expired():
    event = to_event(record("REMOVE", old=room(), identity=TTL_IDENTITY))
    assert event == {"type": "room_expired", "room_id": ROOM_ID}


def test_closed_room_ttl_delete_is_still_room_expired():
    old = room(status="closed", closed_at=TS)
    assert to_event(record("REMOVE", old=old, identity=TTL_IDENTITY)) == {
        "type": "room_expired",
        "room_id": ROOM_ID,
    }


def test_skipped_records():
    skipped = {
        "comment_count only": record(
            "MODIFY", new=idea(comment_count=1), old=idea(comment_count=0)
        ),
        "vote marker insert": record("INSERT", new=vote()),
        "vote marker remove": record("REMOVE", old=vote()),
        "code insert": record("INSERT", new=code()),
        "code remove": record("REMOVE", old=code()),
        "connection insert": record("INSERT", new=connection()),
        "connection remove": record("REMOVE", old=connection()),
        "lookup insert": record("INSERT", new=connection_lookup()),
        "participant rejoin": record(
            "MODIFY", new=participant(display_name="R."), old=participant()
        ),
        "room insert": record("INSERT", new=room()),
        "room modify, status unchanged": record("MODIFY", new=room(topic="x"), old=room()),
        "room remove, not ttl": record("REMOVE", old=room()),
        "idea ttl delete": record("REMOVE", old=idea(), identity=TTL_IDENTITY),
        "comment ttl delete": record("REMOVE", old=comment(), identity=TTL_IDENTITY),
        "participant ttl delete": record("REMOVE", old=participant(), identity=TTL_IDENTITY),
        "connection ttl delete": record("REMOVE", old=connection(), identity=TTL_IDENTITY),
        "unknown entity": record("INSERT", new=idea(entity_type="SOMETHING_NEW")),
    }
    for label, rec in skipped.items():
        assert to_event(rec) is None, label


def test_non_ttl_service_remove_of_room_is_skipped():
    identity = {"type": "Service", "principalId": "other.amazonaws.com"}
    assert to_event(record("REMOVE", old=room(), identity=identity)) is None
