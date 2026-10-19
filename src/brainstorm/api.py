"""HTTP API for the brainstorm board: one Lambda handler that routes every request.

API Gateway (HTTP API, payload format 2.0) calls ``lambda_handler``; ``scripts/serve_local.py``
builds the same events locally. Routes and error codes are listed in docs/api.md.
"""

import base64
import binascii
import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from urllib.parse import unquote

from botocore.exceptions import ClientError

from brainstorm import db, ideas, keys, rooms
from brainstorm.errors import (
    AlreadyVotedError,
    BrainstormError,
    CodeUnavailableError,
    IdeaNotFoundError,
    InvalidInputError,
    NotRoomOwnerError,
    NotVotedError,
    RoomClosedError,
    RoomNotFoundError,
)
from brainstorm.transactions import RETRYABLE_CODES, TransactionCanceledError

logger = logging.getLogger(__name__)

USER_HEADER = "x-user-id"
# User ids go inside keys such as VOTE#<user_id>#<idea_id>, so they must not contain "#".
USER_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
MAX_BODY_BYTES = 16 * 1024
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
# Key attributes, plus owner_id: X-User-Id isn't authenticated, so the owner's id is the
# only thing needed to close a room and must not be handed out.
HIDDEN_KEYS = ("PK", "SK", "GSI1PK", "GSI1SK", "owner_id")

# Data-layer error -> (HTTP status, error code), most specific first.
ERROR_STATUS: list[tuple[type[BrainstormError], int, str]] = [
    (InvalidInputError, 400, "invalid_input"),
    (NotRoomOwnerError, 403, "not_room_owner"),
    (RoomNotFoundError, 404, "room_not_found"),
    (IdeaNotFoundError, 404, "idea_not_found"),
    (RoomClosedError, 409, "room_closed"),
    (AlreadyVotedError, 409, "already_voted"),
    (NotVotedError, 409, "not_voted"),
    (CodeUnavailableError, 503, "code_unavailable"),
]
# DynamoDB errors that mean "too busy right now" rather than a bug.
THROTTLING_CODES = {"ProvisionedThroughputExceededException", "ThrottlingException"}


class ApiError(Exception):
    """An error response raised by the HTTP layer itself (not the data layer)."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass
class Request:
    """The parts of an HTTP request that route handlers use."""

    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)

    @property
    def user_id(self) -> str:
        """Return the caller's ``X-User-Id``.

        Raises:
            ApiError: The header is missing or has characters a user id can't contain.
        """
        user_id = self.headers.get(USER_HEADER, "")
        if not USER_ID_PATTERN.fullmatch(user_id):
            raise ApiError(401, "missing_user", "X-User-Id must be 1-64 letters, digits, _ or -")
        return user_id

    def text(self, name: str) -> str:
        """Return a string field from the JSON body; length checks happen in the data layer."""
        value = self.body.get(name)
        if not isinstance(value, str):
            raise InvalidInputError(f"{name} is required")
        return value


Handler = Callable[[Any, Request], tuple[int, Any]]
ROUTES: list[tuple[str, re.Pattern[str], Handler]] = []


def route(method: str, path: str) -> Callable[[Handler], Handler]:
    """Register a route; ``{name}`` in ``path`` matches one path segment as ``params[name]``."""
    pattern = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", path) + "$")

    def register(handler: Handler) -> Handler:
        ROUTES.append((method, pattern, handler))
        return handler

    return register


def public(item: dict[str, Any]) -> dict[str, Any]:
    """Return an item without key attributes or owner_id; ideas keep ``SK`` as ``idea_sk``."""
    out = {k: v for k, v in item.items() if k not in HIDDEN_KEYS}
    if item.get("entity_type") == "IDEA":
        out["idea_sk"] = item["SK"]
    return out


def encode_cursor(last_key: dict[str, Any] | None) -> str | None:
    """Turn a ``LastEvaluatedKey`` into an opaque URL-safe cursor."""
    if last_key is None:
        return None
    return base64.urlsafe_b64encode(json.dumps(last_key).encode()).decode()


def decode_cursor(cursor: str, room_id: str) -> dict[str, Any]:
    """Turn a cursor back into an ``ExclusiveStartKey``, checking it belongs to this room."""
    try:
        start_key = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (binascii.Error, UnicodeDecodeError, ValueError) as err:
        raise InvalidInputError("cursor is not valid") from err
    # Only accept the exact key shape list_ideas returns, so a forged cursor can't reach
    # another room or make DynamoDB reject the request with a 500.
    if (
        not isinstance(start_key, dict)
        or start_key.keys() != {"PK", "SK"}
        or start_key["PK"] != keys.room_pk(room_id)
        or not isinstance(start_key["SK"], str)
        or not start_key["SK"].startswith("IDEA#")
    ):
        raise InvalidInputError("cursor is not valid for this room")
    return start_key


def page_size(value: str | None) -> int:
    """Parse the ``limit`` query option."""
    if value is None:
        return DEFAULT_PAGE_SIZE
    if not value.isdigit() or not 1 <= int(value) <= MAX_PAGE_SIZE:
        raise InvalidInputError(f"limit must be 1-{MAX_PAGE_SIZE}")
    return int(value)


# --- Routes (pattern numbers refer to docs/data-model.md, section 1) ---


@route("POST", "/rooms")
def create_room(table, req: Request) -> tuple[int, Any]:
    """Create a room owned by the caller (P1)."""
    return 201, public(rooms.create_room(table, req.user_id, req.text("topic")))


@route("GET", "/my-rooms")
def my_rooms(table, req: Request) -> tuple[int, Any]:
    """List the caller's live rooms, newest first (P17)."""
    return 200, {"rooms": [public(r) for r in rooms.list_owner_rooms(table, req.user_id)]}


@route("GET", "/codes/{code}")
def resolve_code(table, req: Request) -> tuple[int, Any]:
    """Find a live room from its join code (P2, P3)."""
    return 200, public(rooms.resolve_code(table, req.params["code"]))


@route("GET", "/rooms/{room_id}")
def load_board(table, req: Request) -> tuple[int, Any]:
    """Load the room and its ideas, optionally with comments (P7, P8)."""
    with_comments = req.query.get("comments", "").lower() in {"true", "1", "yes"}
    board = ideas.load_board(table, req.params["room_id"], include_comments=with_comments)
    return 200, {
        "room": public(board["room"]),
        "ideas": [public(i) for i in board["ideas"]],
        "comments": {
            idea_id: [public(c) for c in comments]
            for idea_id, comments in board["comments"].items()
        },
    }


@route("POST", "/rooms/{room_id}/join")
def join_room(table, req: Request) -> tuple[int, Any]:
    """Join a room or update the caller's display name (P4)."""
    participant = rooms.join_room(
        table, req.params["room_id"], req.user_id, req.text("display_name")
    )
    return 200, public(participant)


@route("GET", "/rooms/{room_id}/participants")
def participants(table, req: Request) -> tuple[int, Any]:
    """List a room's participants (P5)."""
    people = rooms.list_participants(table, req.params["room_id"])
    return 200, {"participants": [public(p) for p in people]}


@route("POST", "/rooms/{room_id}/close")
def close_room(table, req: Request) -> tuple[int, Any]:
    """Close a room; only its owner may (P16)."""
    rooms.close_room(table, req.params["room_id"], req.user_id)
    return 204, None


@route("POST", "/rooms/{room_id}/ideas")
def post_idea(table, req: Request) -> tuple[int, Any]:
    """Post an idea to an open room (P6)."""
    idea = ideas.post_idea(
        table, req.params["room_id"], req.user_id, req.text("display_name"), req.text("body")
    )
    return 201, public(idea)


@route("GET", "/rooms/{room_id}/ideas")
def list_ideas(table, req: Request) -> tuple[int, Any]:
    """Return one page of ideas, newest first (P9)."""
    room_id = req.params["room_id"]
    cursor = req.query.get("cursor")
    start_key = decode_cursor(cursor, room_id) if cursor else None
    items, last_key = ideas.list_ideas(table, room_id, page_size(req.query.get("limit")), start_key)
    return 200, {"ideas": [public(i) for i in items], "cursor": encode_cursor(last_key)}


@route("PUT", "/rooms/{room_id}/ideas/{idea_sk}/vote")
def vote(table, req: Request) -> tuple[int, Any]:
    """Vote for an idea, once per user (P11)."""
    ideas.vote(table, req.params["room_id"], req.user_id, req.params["idea_sk"])
    return 204, None


@route("DELETE", "/rooms/{room_id}/ideas/{idea_sk}/vote")
def unvote(table, req: Request) -> tuple[int, Any]:
    """Take back the caller's vote (P12)."""
    ideas.unvote(table, req.params["room_id"], req.user_id, req.params["idea_sk"])
    return 204, None


@route("GET", "/rooms/{room_id}/my-votes")
def my_votes(table, req: Request) -> tuple[int, Any]:
    """Return the ids of the ideas the caller voted for (P13)."""
    voted = ideas.my_votes(table, req.params["room_id"], req.user_id)
    return 200, {"idea_ids": sorted(voted)}


@route("POST", "/rooms/{room_id}/ideas/{idea_sk}/comments")
def add_comment(table, req: Request) -> tuple[int, Any]:
    """Comment on an idea (P14)."""
    comment = ideas.add_comment(
        table,
        req.params["room_id"],
        req.params["idea_sk"],
        req.user_id,
        req.text("display_name"),
        req.text("body"),
    )
    return 201, public(comment)


@route("GET", "/rooms/{room_id}/ideas/{idea_sk}/comments")
def list_comments(table, req: Request) -> tuple[int, Any]:
    """Return the comments on one idea, oldest first (P15)."""
    comments = ideas.list_comments(table, req.params["room_id"], req.params["idea_sk"])
    return 200, {"comments": [public(c) for c in comments]}


# --- Event handling ---


def _json_default(value: Any) -> Any:
    """Encode the ``Decimal`` numbers boto3 returns as JSON ints or floats."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"can't encode {type(value).__name__} as JSON")


def response(status: int, payload: Any = None) -> dict[str, Any]:
    """Build an API Gateway (payload 2.0) response with CORS headers."""
    headers = {
        "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "*"),
        "Access-Control-Allow-Headers": "Content-Type, X-User-Id",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    }
    if payload is None:
        return {"statusCode": status, "headers": headers, "body": ""}
    headers["Content-Type"] = "application/json"
    return {
        "statusCode": status,
        "headers": headers,
        "body": json.dumps(payload, default=_json_default),
    }


def error(status: int, code: str, message: str) -> dict[str, Any]:
    """Build a JSON error response."""
    return response(status, {"error": code, "message": message})


def parse_body(event: dict[str, Any]) -> dict[str, Any]:
    """Decode the event body as a JSON object (empty if there is no body)."""
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw, validate=True).decode()
        except (binascii.Error, UnicodeDecodeError) as err:
            raise InvalidInputError("request body is not valid base64 UTF-8") from err
    if not raw:
        return {}
    if len(raw.encode()) > MAX_BODY_BYTES:
        raise InvalidInputError("request body is too large")
    try:
        body = json.loads(raw)
    except ValueError as err:
        raise InvalidInputError("request body is not valid JSON") from err
    if not isinstance(body, dict):
        raise InvalidInputError("request body must be a JSON object")
    return body


def match(method: str, path: str) -> tuple[Handler, dict[str, str]] | None:
    """Find the handler and decoded path parameters for a request, or None."""
    for route_method, pattern, handler in ROUTES:
        found = pattern.match(path)
        if found and route_method == method:
            return handler, {k: unquote(v) for k, v in found.groupdict().items()}
    return None


def handle(table, event: dict[str, Any]) -> dict[str, Any]:
    """Route one API Gateway event to its handler and turn the result into a response."""
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "GET").upper()
    # rawPath keeps percent-encoding, so an encoded "/" can't split an idea key across segments.
    path = event.get("rawPath") or http.get("path", "/")
    if method == "OPTIONS":
        return response(204)
    found = match(method, path)
    if found is None:
        return error(404, "not_found", f"no route for {method} {path}")
    handler, params = found

    try:
        req = Request(
            method=method,
            path=path,
            headers={k.lower(): v for k, v in (event.get("headers") or {}).items()},
            query=event.get("queryStringParameters") or {},
            body=parse_body(event),
            params=params,
        )
        status, payload = handler(table, req)
        return response(status, payload)
    except ApiError as err:
        return error(err.status, err.code, str(err))
    except BrainstormError as err:
        for error_type, status, code in ERROR_STATUS:
            if isinstance(err, error_type):
                return error(status, code, str(err) or code)
        raise
    except TransactionCanceledError as err:
        if RETRYABLE_CODES & set(err.codes):
            # transact_write ran out of retries on conflicts or throttling.
            logger.warning("transaction still failing after retries: %s %s", method, path)
            return error(503, "busy", "the database is busy, please try again")
        logger.exception("unexpected transaction failure on %s %s", method, path)
        return error(500, "internal_error", "something went wrong")
    except ClientError as err:
        if err.response["Error"]["Code"] in THROTTLING_CODES:
            return error(503, "busy", "the database is busy, please try again")
        logger.exception("DynamoDB error on %s %s", method, path)
        return error(500, "internal_error", "something went wrong")
    except Exception:
        logger.exception("unhandled error on %s %s", method, path)
        return error(500, "internal_error", "something went wrong")


_table = None


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entry point; the table resource is reused while the function stays warm."""
    global _table
    if _table is None:
        _table = db.table()
    return handle(_table, event)
