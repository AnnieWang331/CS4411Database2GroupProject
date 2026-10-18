"""Idea operations: post, load board, vote, unvote, comment.

An idea is addressed by its sort key (``idea_sk``, returned as ``SK`` on every idea item), so
votes and comments can update the idea without a lookup. Access-pattern numbers refer to
docs/data-model.md, section 1.
"""

from typing import Any

from boto3.dynamodb.conditions import Key

from brainstorm import keys
from brainstorm.errors import (
    AlreadyVotedError,
    IdeaNotFoundError,
    InvalidInputError,
    NotVotedError,
    RoomClosedError,
    RoomNotFoundError,
)
from brainstorm.rooms import get_room, is_live, open_room_check, query_all, require_text
from brainstorm.transactions import TransactionCanceledError, transact_write

MAX_IDEA_LENGTH = 500
MAX_COMMENT_LENGTH = 300


def idea_id_from_sk(idea_sk: str) -> str:
    """Return the idea id from an idea sort key (``IDEA#<created_at>#<idea_id>``)."""
    prefix, _, idea_id = idea_sk.rpartition("#")
    if not prefix.startswith("IDEA#") or not idea_id:
        raise InvalidInputError(f"not an idea key: {idea_sk!r}")
    return idea_id


def post_idea(table, room_id: str, author_id: str, author_name: str, body: str) -> dict[str, Any]:
    """Post an idea to an open room and return the idea item (pattern 6).

    Raises:
        RoomNotFoundError: The room doesn't exist or has expired.
        RoomClosedError: The room is closed (checked inside the transaction).
    """
    body = require_text(body, "body", MAX_IDEA_LENGTH)
    room = get_room(table, room_id)
    created_at, idea_id = keys.iso(keys.utc_now()), keys.new_id()
    idea = {
        "PK": keys.room_pk(room_id),
        "SK": keys.idea_sk(created_at, idea_id),
        "entity_type": "IDEA",
        "idea_id": idea_id,
        "author_id": author_id,
        "author_name": author_name,
        "body": body,
        "vote_count": 0,
        "comment_count": 0,
        "created_at": created_at,
        "expires_at": room["expires_at"],
    }
    try:
        transact_write(
            table,
            [
                # Checking expires_at = :exp guarantees the idea gets the room's TTL.
                open_room_check(room_id, room["expires_at"]),
                {"Put": {"Item": idea, "ConditionExpression": "attribute_not_exists(PK)"}},
            ],
        )
    except TransactionCanceledError as err:
        if err.failed(0):
            raise RoomClosedError(room_id) from err
        raise
    return idea


def load_board(table, room_id: str, include_comments: bool = False) -> dict[str, Any]:
    """Load a room's META and ideas (newest first) with one Query (patterns 7 and 8).

    Returns:
        ``{"room": <META item>, "ideas": [...], "comments": {idea_id: [oldest first]}}``;
        ``comments`` is empty unless ``include_comments`` is set.

    Raises:
        RoomNotFoundError: The room doesn't exist or has expired.
    """
    pk = Key("PK").eq(keys.room_pk(room_id))
    # SK order is COMMENT# < IDEA# < META, so one range covers META, ideas and, optionally,
    # comments; participants (USER#) and vote markers (VOTE#) sort after META and are skipped.
    sk = Key("SK").lte(keys.META) if include_comments else Key("SK").between("IDEA#", keys.META)
    items = query_all(table, KeyConditionExpression=pk & sk, ScanIndexForward=False)

    if not items or items[0]["SK"] != keys.META or not is_live(items[0]):
        raise RoomNotFoundError(room_id)
    board: dict[str, Any] = {"room": items[0], "ideas": [], "comments": {}}
    for item in items[1:]:
        if item["entity_type"] == "IDEA":
            board["ideas"].append(item)
        elif item["entity_type"] == "COMMENT":
            board["comments"].setdefault(item["idea_id"], []).insert(0, item)
    return board


def list_ideas(
    table, room_id: str, limit: int = 20, start_key: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Return one page of ideas, newest first, and the key to continue from (pattern 9)."""
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("PK").eq(keys.room_pk(room_id))
        & Key("SK").begins_with("IDEA#"),
        "ScanIndexForward": False,
        "Limit": limit,
    }
    if start_key:
        kwargs["ExclusiveStartKey"] = start_key
    page = table.query(**kwargs)
    return page["Items"], page.get("LastEvaluatedKey")


def top_ideas(board: dict[str, Any], n: int = 10) -> list[dict[str, Any]]:
    """Return the ``n`` most-voted ideas from a loaded board, sorted client-side (pattern 10)."""
    return sorted(board["ideas"], key=lambda idea: idea["vote_count"], reverse=True)[:n]


def _idea_update(room_id: str, idea_sk: str, expression: str, **extra: Any) -> dict[str, Any]:
    """Build an Update on an existing idea (the condition stops ADD creating a stray item)."""
    update: dict[str, Any] = {
        "Key": {"PK": keys.room_pk(room_id), "SK": idea_sk},
        "UpdateExpression": expression,
        "ConditionExpression": "attribute_exists(PK)",
    }
    update.update(extra)
    return {"Update": update}


def vote(table, room_id: str, user_id: str, idea_sk: str) -> None:
    """Record one vote per user per idea and increment the idea's counter atomically (pattern 11).

    Raises:
        RoomClosedError: The room is closed or expired.
        AlreadyVotedError: The user already voted for this idea.
        IdeaNotFoundError: No such idea in this room.
    """
    idea_id = idea_id_from_sk(idea_sk)
    now = keys.utc_now()
    room = get_room(table, room_id)
    marker = {
        "PK": keys.room_pk(room_id),
        "SK": keys.vote_sk(user_id, idea_id),
        "entity_type": "VOTE",
        "user_id": user_id,
        "idea_id": idea_id,
        "idea_sk": idea_sk,
        "created_at": keys.iso(now),
        "expires_at": room["expires_at"],
    }
    try:
        transact_write(
            table,
            [
                open_room_check(room_id),
                {"Put": {"Item": marker, "ConditionExpression": "attribute_not_exists(PK)"}},
                _idea_update(
                    room_id,
                    idea_sk,
                    "ADD vote_count :one",
                    ExpressionAttributeValues={":one": 1},
                ),
            ],
        )
    except TransactionCanceledError as err:
        if err.failed(0):
            raise RoomClosedError(room_id) from err
        if err.failed(2):
            raise IdeaNotFoundError(idea_sk) from err
        if err.failed(1):
            raise AlreadyVotedError(idea_sk) from err
        raise


def unvote(table, room_id: str, user_id: str, idea_sk: str) -> None:
    """Remove a user's vote and decrement the idea's counter atomically (pattern 12).

    Raises:
        RoomClosedError: The room is closed or expired.
        NotVotedError: The user hasn't voted for this idea.
        IdeaNotFoundError: No such idea in this room.
    """
    idea_id = idea_id_from_sk(idea_sk)
    try:
        transact_write(
            table,
            [
                open_room_check(room_id),
                {
                    "Delete": {
                        "Key": {
                            "PK": keys.room_pk(room_id),
                            "SK": keys.vote_sk(user_id, idea_id),
                        },
                        "ConditionExpression": "attribute_exists(PK)",
                    }
                },
                _idea_update(
                    room_id,
                    idea_sk,
                    "ADD vote_count :minus_one",
                    ConditionExpression="attribute_exists(PK) AND vote_count > :zero",
                    ExpressionAttributeValues={":minus_one": -1, ":zero": 0},
                ),
            ],
        )
    except TransactionCanceledError as err:
        if err.failed(0):
            raise RoomClosedError(room_id) from err
        if err.failed(1):
            raise NotVotedError(idea_sk) from err
        if err.failed(2):
            raise IdeaNotFoundError(idea_sk) from err
        raise


def my_votes(table, room_id: str, user_id: str) -> set[str]:
    """Return the ids of the ideas a user has voted for in a room (pattern 13)."""
    markers = query_all(
        table,
        KeyConditionExpression=Key("PK").eq(keys.room_pk(room_id))
        & Key("SK").begins_with(f"VOTE#{user_id}#"),
    )
    return {marker["idea_id"] for marker in markers}


def add_comment(
    table, room_id: str, idea_sk: str, author_id: str, author_name: str, body: str
) -> dict[str, Any]:
    """Comment on an idea and increment its comment counter atomically (pattern 14).

    Raises:
        RoomNotFoundError: The room doesn't exist or has expired.
        RoomClosedError: The room is closed.
        IdeaNotFoundError: No such idea in this room.
    """
    idea_id = idea_id_from_sk(idea_sk)
    body = require_text(body, "body", MAX_COMMENT_LENGTH)
    room = get_room(table, room_id)
    created_at, comment_id = keys.iso(keys.utc_now()), keys.new_id()
    comment = {
        "PK": keys.room_pk(room_id),
        "SK": keys.comment_sk(idea_id, created_at, comment_id),
        "entity_type": "COMMENT",
        "comment_id": comment_id,
        "idea_id": idea_id,
        "author_id": author_id,
        "author_name": author_name,
        "body": body,
        "created_at": created_at,
        "expires_at": room["expires_at"],
    }
    try:
        transact_write(
            table,
            [
                open_room_check(room_id, room["expires_at"]),
                {"Put": {"Item": comment, "ConditionExpression": "attribute_not_exists(PK)"}},
                _idea_update(
                    room_id,
                    idea_sk,
                    "ADD comment_count :one",
                    ExpressionAttributeValues={":one": 1},
                ),
            ],
        )
    except TransactionCanceledError as err:
        if err.failed(0):
            raise RoomClosedError(room_id) from err
        if err.failed(2):
            raise IdeaNotFoundError(idea_sk) from err
        raise
    return comment


def list_comments(table, room_id: str, idea_sk: str) -> list[dict[str, Any]]:
    """Return the comments on one idea, oldest first (pattern 15)."""
    return query_all(
        table,
        KeyConditionExpression=Key("PK").eq(keys.room_pk(room_id))
        & Key("SK").begins_with(f"COMMENT#{idea_id_from_sk(idea_sk)}#"),
    )
