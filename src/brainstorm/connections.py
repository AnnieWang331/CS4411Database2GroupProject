"""WebSocket connections: which clients are subscribed to a room's live updates.

Each connection is stored twice: ``ROOM#<room_id>`` / ``WS#<connection_id>`` so the stream
broadcaster can list a room's connections with one Query, and ``CONN#<connection_id>`` / ``META``
so ``$disconnect`` (which only gets the connection id) can find the room. Access-pattern numbers
refer to docs/data-model.md, section 1.
"""

import logging
from typing import Any

from boto3.dynamodb.conditions import Key

from brainstorm import keys
from brainstorm.errors import InvalidInputError, RoomClosedError
from brainstorm.rooms import OPEN, get_room, is_live, query_all
from brainstorm.transactions import transact_write

# Room ids are 32 hex characters and API Gateway connection ids are about 16; the cap keeps a bad
# query string from building a key over DynamoDB's size limit (a 500 instead of a 400).
MAX_ID_LENGTH = 128

logger = logging.getLogger(__name__)


def require_id(value: str, name: str) -> str:
    """Check an id from outside (query string, API Gateway) can go inside a key."""
    if not value or "#" in value or len(value) > MAX_ID_LENGTH:
        raise InvalidInputError(f"not a valid {name}: {value[:MAX_ID_LENGTH]!r}")
    return value


def connect(table, room_id: str, connection_id: str) -> dict[str, Any]:
    """Subscribe a connection to an open room and return the connection item (pattern 19).

    The open-room check is a read, not a ConditionCheck: a check on the room item would make every
    connect conflict with the class's other connects, posts and votes. Instead the room is read
    again (strongly consistent) after the write. If it closed in between, the connection is
    removed and refused. If it closes after that second read, the close comes after our write, so
    the live-update function's (consistent) list of connections includes this one. If the second
    read fails for any other reason (throttling, say), the connection is removed too, so a refused
    socket never leaves items behind for the broadcaster.

    Raises:
        InvalidInputError: The room or connection id can't be used in a key.
        RoomNotFoundError: The room doesn't exist or has expired.
        RoomClosedError: The room is closed.
    """
    room_id = require_id(room_id, "room id")
    connection_id = require_id(connection_id, "connection id")
    room = get_room(table, room_id, consistent=True)
    if room["status"] != OPEN:
        raise RoomClosedError(room_id)
    common = {
        "entity_type": "CONNECTION",
        "connection_id": connection_id,
        "room_id": room_id,
        "connected_at": keys.iso(keys.utc_now()),
        "expires_at": room["expires_at"],
    }
    connection = {"PK": keys.room_pk(room_id), "SK": keys.connection_sk(connection_id), **common}
    lookup = {
        **common,
        "PK": keys.connection_pk(connection_id),
        "SK": keys.META,
        "entity_type": "CONNECTION_LOOKUP",
    }
    # Both items or neither, so a disconnect can always find and remove the room's item.
    transact_write(table, [{"Put": {"Item": connection}}, {"Put": {"Item": lookup}}])
    try:
        room = get_room(table, room_id, consistent=True)
        if room["status"] != OPEN:
            raise RoomClosedError(room_id)
    except Exception:
        _undo_connect(table, room_id, connection_id)
        raise
    return connection


def disconnect(table, connection_id: str) -> str | None:
    """Remove a connection and return its room id, or None if it wasn't stored (pattern 20).

    Doesn't check the room: a socket on a closed or expired room still has to be cleaned up.
    """
    connection_id = require_id(connection_id, "connection id")
    lookup = table.get_item(
        Key={"PK": keys.connection_pk(connection_id), "SK": keys.META}, ConsistentRead=True
    ).get("Item")
    if lookup is None:
        return None
    room_id = lookup["room_id"]
    _delete(table, room_id, connection_id)
    return room_id


def _undo_connect(table, room_id: str, connection_id: str) -> None:
    """Remove a connection that is being refused, without hiding why it was refused.

    If the delete fails too, the items stay until a send fails with ``GoneException`` or TTL
    removes them, so it's logged rather than raised.
    """
    try:
        _delete(table, room_id, connection_id)
    except Exception:
        logger.warning("couldn't remove refused connection %s", connection_id, exc_info=True)


def _delete(table, room_id: str, connection_id: str) -> None:
    """Delete a connection's room item and lookup item together."""
    transact_write(
        table,
        [
            {
                "Delete": {
                    "Key": {"PK": keys.room_pk(room_id), "SK": keys.connection_sk(connection_id)}
                }
            },
            {"Delete": {"Key": {"PK": keys.connection_pk(connection_id), "SK": keys.META}}},
        ],
    )


def list_connections(table, room_id: str) -> list[dict[str, Any]]:
    """Return a room's live connections (pattern 21).

    Strongly consistent, so a connection whose write finished before a close is always listed (see
    ``connect``).
    """
    items = query_all(
        table,
        KeyConditionExpression=Key("PK").eq(keys.room_pk(room_id))
        & Key("SK").begins_with(keys.CONNECTION_PREFIX),
        ConsistentRead=True,
    )
    return [item for item in items if is_live(item)]
