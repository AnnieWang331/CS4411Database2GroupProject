"""WebSocket API for live updates: API Gateway's ``$connect``, ``$disconnect`` and ``$default``.

A client opens ``wss://.../?room_id=<room_id>`` (browsers can't set headers on a WebSocket, so the
room goes in the query string). Returning a non-2xx status from ``$connect`` refuses the
connection. Clients never send anything we act on: updates only flow from the server.
"""

import logging
from typing import Any

from botocore.exceptions import ClientError

from brainstorm import connections, db
from brainstorm.api import ERROR_STATUS, THROTTLING_CODES
from brainstorm.errors import BrainstormError
from brainstorm.transactions import RETRYABLE_CODES, TransactionCanceledError

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
    except BrainstormError as err:
        status = ERROR_STATUS[type(err)][0]
    except TransactionCanceledError as err:
        if RETRYABLE_CODES & set(err.codes):
            # transact_write ran out of retries on conflicts or throttling.
            logger.warning("transaction still failing after retries on %s", route_key)
            status = 503
        else:
            logger.exception("unexpected transaction failure on %s", route_key)
            status = 500
    except ClientError as err:
        if err.response["Error"]["Code"] in THROTTLING_CODES:
            logger.warning("throttled on %s", route_key)
            status = 503
        else:
            logger.exception("DynamoDB error on %s", route_key)
            status = 500
    except Exception:
        logger.exception("unhandled error on %s", route_key)
        status = 500
    return {"statusCode": status}


_table = None


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entry point; the table resource is reused while the function stays warm."""
    global _table
    if _table is None:
        _table = db.table()
    return handle(_table, event)
