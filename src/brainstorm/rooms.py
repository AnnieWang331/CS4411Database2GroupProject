"""Room operations: create, resolve code, join, participants, close, list owner's rooms.

Access-pattern numbers refer to docs/data-model.md, section 1.
"""

from datetime import timedelta
from typing import Any

from boto3.dynamodb.conditions import Key

from brainstorm import keys, schema
from brainstorm.errors import (
    CodeUnavailableError,
    InvalidInputError,
    NotRoomOwnerError,
    RoomClosedError,
    RoomNotFoundError,
)
from brainstorm.transactions import TransactionCanceledError, transact_write

DEFAULT_TTL = timedelta(hours=24)
MAX_CODE_ATTEMPTS = 5
MAX_TOPIC_LENGTH = 200
MAX_NAME_LENGTH = 50

OPEN = "open"
CLOSED = "closed"
STATUS = {"#status": "status"}


def require_text(value: str, field: str, max_length: int) -> str:
    """Strip ``value`` and check it is non-empty and at most ``max_length`` characters."""
    value = value.strip()
    if not value or len(value) > max_length:
        raise InvalidInputError(f"{field} must be 1-{max_length} characters")
    return value


def is_live(item: dict[str, Any]) -> bool:
    """Return True if ``item`` hasn't passed its TTL (TTL deletion can lag by days)."""
    return item["expires_at"] > keys.epoch(keys.utc_now())


def create_room(table, owner_id: str, topic: str, ttl: timedelta = DEFAULT_TTL) -> dict[str, Any]:
    """Create an open room with a unique join code and return its META item (pattern 1).

    Raises:
        CodeUnavailableError: Every generated code was taken.
    """
    topic = require_text(topic, "topic", MAX_TOPIC_LENGTH)
    now = keys.utc_now()
    created_at = keys.iso(now)
    expires_at = keys.epoch(now + ttl)

    for _ in range(MAX_CODE_ATTEMPTS):
        room_id, code = keys.new_id(), keys.new_code()
        room = {
            "PK": keys.room_pk(room_id),
            "SK": keys.META,
            "GSI1PK": keys.user_key(owner_id),
            "GSI1SK": keys.owner_room_sk(created_at, room_id),
            "entity_type": "ROOM",
            "room_id": room_id,
            "code": code,
            "topic": topic,
            "status": OPEN,
            "owner_id": owner_id,
            "created_at": created_at,
            "expires_at": expires_at,
        }
        code_item = {
            "PK": keys.code_pk(code),
            "SK": keys.META,
            "entity_type": "ROOM_CODE",
            "code": code,
            "room_id": room_id,
            "created_at": created_at,
            "expires_at": expires_at,
        }
        try:
            transact_write(
                table,
                [
                    {"Put": {"Item": room, "ConditionExpression": "attribute_not_exists(PK)"}},
                    {
                        "Put": {
                            "Item": code_item,
                            # An expired code may linger until TTL deletes it; allow reuse.
                            "ConditionExpression": "attribute_not_exists(PK) OR expires_at < :now",
                            "ExpressionAttributeValues": {":now": keys.epoch(now)},
                        }
                    },
                ],
            )
            return room
        except TransactionCanceledError as err:
            if not (err.failed(0) or err.failed(1)):
                raise
            # Code taken (or, very unlikely, room id collision): try new values.
    raise CodeUnavailableError(f"no free join code after {MAX_CODE_ATTEMPTS} attempts")


def get_room(table, room_id: str) -> dict[str, Any]:
    """Return a live room's META item (pattern 3).

    Raises:
        RoomNotFoundError: The room doesn't exist or has expired.
    """
    item = table.get_item(Key={"PK": keys.room_pk(room_id), "SK": keys.META}).get("Item")
    if item is None or not is_live(item):
        raise RoomNotFoundError(room_id)
    return item


def resolve_code(table, code: str) -> dict[str, Any]:
    """Return the live room for a join code (pattern 2, then 3).

    Raises:
        RoomNotFoundError: The code is unknown, freed by a close, or expired.
    """
    code = code.strip().upper()
    item = table.get_item(Key={"PK": keys.code_pk(code), "SK": keys.META}, ConsistentRead=True).get(
        "Item"
    )
    if item is None or not is_live(item):
        raise RoomNotFoundError(code)
    return get_room(table, item["room_id"])


def open_room_check(room_id: str, expires_at: int | None = None) -> dict[str, Any]:
    """Build a ConditionCheck that the room is open, live and (optionally) has this TTL."""
    condition = "#status = :open AND expires_at > :now"
    values: dict[str, Any] = {":open": OPEN, ":now": keys.epoch(keys.utc_now())}
    if expires_at is not None:
        condition += " AND expires_at = :exp"
        values[":exp"] = expires_at
    return {
        "ConditionCheck": {
            "Key": {"PK": keys.room_pk(room_id), "SK": keys.META},
            "ConditionExpression": condition,
            "ExpressionAttributeNames": STATUS,
            "ExpressionAttributeValues": values,
        }
    }


def join_room(table, room_id: str, user_id: str, display_name: str) -> dict[str, Any]:
    """Add or update a participant in an open room and return the participant item (pattern 4).

    Raises:
        RoomNotFoundError: The room doesn't exist or has expired.
        RoomClosedError: The room is closed.
    """
    display_name = require_text(display_name, "display_name", MAX_NAME_LENGTH)
    room = get_room(table, room_id)
    joined_at = keys.iso(keys.utc_now())
    try:
        transact_write(
            table,
            [
                open_room_check(room_id),
                {
                    "Update": {
                        "Key": {"PK": keys.room_pk(room_id), "SK": keys.user_key(user_id)},
                        "UpdateExpression": (
                            "SET entity_type = :pt, user_id = :u, display_name = :dn, "
                            "joined_at = if_not_exists(joined_at, :ts), expires_at = :exp"
                        ),
                        "ExpressionAttributeValues": {
                            ":pt": "PARTICIPANT",
                            ":u": user_id,
                            ":dn": display_name,
                            ":ts": joined_at,
                            ":exp": room["expires_at"],
                        },
                    }
                },
            ],
        )
    except TransactionCanceledError as err:
        if err.failed(0):
            raise RoomClosedError(room_id) from err
        raise
    return table.get_item(
        Key={"PK": keys.room_pk(room_id), "SK": keys.user_key(user_id)}, ConsistentRead=True
    )["Item"]


def query_all(table, **kwargs: Any) -> list[dict[str, Any]]:
    """Run a Query and follow ``LastEvaluatedKey`` until every page is read."""
    items: list[dict[str, Any]] = []
    while True:
        page = table.query(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def list_participants(table, room_id: str) -> list[dict[str, Any]]:
    """Return a room's participants (pattern 5)."""
    return query_all(
        table,
        KeyConditionExpression=Key("PK").eq(keys.room_pk(room_id)) & Key("SK").begins_with("USER#"),
    )


def close_room(table, room_id: str, owner_id: str) -> None:
    """Close a room and free its join code (pattern 16).

    Raises:
        RoomNotFoundError: The room doesn't exist or has expired.
        NotRoomOwnerError: ``owner_id`` isn't the room's owner.
        RoomClosedError: The room is already closed.
    """
    room = get_room(table, room_id)
    try:
        transact_write(
            table,
            [
                {
                    "Update": {
                        "Key": {"PK": keys.room_pk(room_id), "SK": keys.META},
                        "UpdateExpression": "SET #status = :closed, closed_at = :ts",
                        "ConditionExpression": (
                            "owner_id = :uid AND #status = :open AND expires_at > :now"
                        ),
                        "ExpressionAttributeNames": STATUS,
                        "ExpressionAttributeValues": {
                            ":closed": CLOSED,
                            ":open": OPEN,
                            ":ts": keys.iso(keys.utc_now()),
                            ":uid": owner_id,
                            ":now": keys.epoch(keys.utc_now()),
                        },
                    }
                },
                {
                    "Delete": {
                        "Key": {"PK": keys.code_pk(room["code"]), "SK": keys.META},
                        # Don't fail if TTL already removed it; don't delete a reused code (only
                        # possible once this room has expired, which the update above rejects).
                        "ConditionExpression": "attribute_not_exists(PK) OR room_id = :rid",
                        "ExpressionAttributeValues": {":rid": room_id},
                    }
                },
            ],
        )
    except TransactionCanceledError as err:
        if not err.failed(0):
            raise
        # The condition already enforced the rule; this read only picks the error to report.
        current = get_room(table, room_id)  # raises RoomNotFoundError if it just expired
        if current["owner_id"] != owner_id:
            raise NotRoomOwnerError(room_id) from err
        raise RoomClosedError(room_id) from err


def list_owner_rooms(table, owner_id: str) -> list[dict[str, Any]]:
    """Return an owner's live rooms, newest first, from the sparse GSI1 (pattern 17)."""
    rooms = query_all(
        table,
        IndexName=schema.GSI1,
        KeyConditionExpression=Key("GSI1PK").eq(keys.user_key(owner_id)),
        ScanIndexForward=False,
    )
    return [room for room in rooms if is_live(room)]
