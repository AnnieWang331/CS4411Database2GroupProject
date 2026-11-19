"""WebSocket connections: which clients are subscribed to a room's live updates.

Each connection is stored twice: ``ROOM#<room_id>`` / ``WS#<connection_id>`` so the stream
broadcaster can list a room's connections with one Query, and ``CONN#<connection_id>`` / ``META``
so ``$disconnect`` (which only gets the connection id) can find the room. Access-pattern numbers
refer to docs/data-model.md, section 1.
"""

from typing import Any

from boto3.dynamodb.conditions import Key

from brainstorm import keys
from brainstorm.errors import InvalidInputError, RoomClosedError
from brainstorm.rooms import OPEN, get_room, is_live, query_all
from brainstorm.transactions import transact_write


def require_connection_id(connection_id: str) -> str:
    """Check a connection id can go inside a key (API Gateway doesn't promise its format)."""
    if not connection_id or "#" in connection_id:
        raise InvalidInputError(f"not a valid connection id: {connection_id!r}")
    return connection_id


def connect(table, room_id: str, connection_id: str) -> dict[str, Any]:
    """Subscribe a connection to an open room and return the connection item (pattern 19).

    The open-room check is a read, not a ConditionCheck: a check on the room item would make every
    connect conflict with the class's other connects, posts and votes. If the room closes between
    the read and the write, the extra subscriber just receives ``room_closed``.

    Raises:
        RoomNotFoundError: The room doesn't exist or has expired.
        RoomClosedError: The room is closed.
    """
    connection_id = require_connection_id(connection_id)
    room = get_room(table, room_id)
    if room["status"] != OPEN:
        raise RoomClosedError(room_id)
    connected_at = keys.iso(keys.utc_now())
    connection = {
        "PK": keys.room_pk(room_id),
        "SK": keys.connection_sk(connection_id),
        "entity_type": "CONNECTION",
        "connection_id": connection_id,
        "room_id": room_id,
        "connected_at": connected_at,
        "expires_at": room["expires_at"],
    }
    lookup = {
        "PK": keys.connection_pk(connection_id),
        "SK": keys.META,
        "entity_type": "CONNECTION_LOOKUP",
        "connection_id": connection_id,
        "room_id": room_id,
        "connected_at": connected_at,
        "expires_at": room["expires_at"],
    }
    # Both items or neither, so a disconnect can always find and remove the room's item.
    transact_write(table, [{"Put": {"Item": connection}}, {"Put": {"Item": lookup}}])
    return connection


def disconnect(table, connection_id: str) -> str | None:
    """Remove a connection and return its room id, or None if it wasn't stored (pattern 20).

    Doesn't check the room: a socket on a closed or expired room still has to be cleaned up.
    """
    connection_id = require_connection_id(connection_id)
    lookup = table.get_item(
        Key={"PK": keys.connection_pk(connection_id), "SK": keys.META}, ConsistentRead=True
    ).get("Item")
    if lookup is None:
        return None
    room_id = lookup["room_id"]
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
    return room_id


def list_connections(table, room_id: str) -> list[dict[str, Any]]:
    """Return a room's live connections (pattern 21)."""
    items = query_all(
        table,
        KeyConditionExpression=Key("PK").eq(keys.room_pk(room_id)) & Key("SK").begins_with("WS#"),
    )
    return [item for item in items if is_live(item)]
