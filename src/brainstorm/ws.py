"""WebSocket API for live updates: API Gateway's ``$connect``, ``$disconnect`` and ``$default``.

A client opens ``wss://.../?room_id=<room_id>`` (browsers can't set headers on a WebSocket, so the
room goes in the query string). Returning a non-2xx status from ``$connect`` refuses the
connection. Clients never send anything we act on: updates only flow from the server.
"""

import logging
from typing import Any

from brainstorm import connections, db
from brainstorm.errors import classify_error

logger = logging.getLogger(__name__)


def on_connect(table, connection_id: str, query: dict[str, str]) -> int:
    """Store the connection for its room; refuse it if the room isn't open."""
    room_id = query.get("room_id", "")
    if not room_id:
        return 400
    connections.connect(table, room_id, connection_id)
    return 200


def on_disconnect(table, connection_id: str) -> int:
    """Forget the connection (best effort: API Gateway may never send this event)."""
    connections.disconnect(table, connection_id)
    return 200


def handle(table, event: dict[str, Any]) -> dict[str, Any]:
    """Route one WebSocket event by its route key and return the status for API Gateway."""
    context = event.get("requestContext", {})
    route_key = context.get("routeKey")
    connection_id = context.get("connectionId", "")
    try:
        if route_key == "$connect":
            status = on_connect(table, connection_id, event.get("queryStringParameters") or {})
        elif route_key == "$disconnect":
            status = on_disconnect(table, connection_id)
        else:
            status = 200  # $default: ignore messages from clients
    except Exception as err:
        info = classify_error(err)
        if info.log_level is not None:
            logger.log(
                info.log_level,
                "%s on %s",
                info.code,
                route_key,
                exc_info=info.log_level >= logging.ERROR,
            )
        status = info.status
    return {"statusCode": status}


_table = None


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entry point; the table resource is reused while the function stays warm."""
    global _table
    if _table is None:
        _table = db.table()
    return handle(_table, event)
