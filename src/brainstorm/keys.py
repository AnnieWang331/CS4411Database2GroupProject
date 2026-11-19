"""Key builders, ids, join codes, and timestamps for the single-table design."""

import secrets
import uuid
from datetime import UTC, datetime

META = "META"
# Join-code alphabet without look-alike characters (no I, L, O, 0, 1).
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6
# Sort-key prefix of a room's connection items (pattern 21 queries on it).
CONNECTION_PREFIX = "WS#"


def utc_now() -> datetime:
    """Return the current UTC time (tests monkeypatch this to control the clock)."""
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    """Format a datetime as fixed-width ISO 8601 UTC with milliseconds, so it sorts lexically."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def epoch(dt: datetime) -> int:
    """Return a datetime as whole epoch seconds (the TTL attribute format)."""
    return int(dt.timestamp())


def new_id() -> str:
    """Return a new random id."""
    return uuid.uuid4().hex


def new_code() -> str:
    """Return a random human-friendly join code."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def room_pk(room_id: str) -> str:
    """Partition key of a room's item collection."""
    return f"ROOM#{room_id}"


def room_id_from_pk(pk: str) -> str | None:
    """Return the room id in a ``ROOM#<room_id>`` partition key, or ``None`` for other keys."""
    prefix = room_pk("")
    if pk.startswith(prefix) and len(pk) > len(prefix):
        return pk[len(prefix) :]
    return None


def code_pk(code: str) -> str:
    """Partition key of a join-code item."""
    return f"CODE#{code}"


def user_key(user_id: str) -> str:
    """Participant sort key, also the GSI1 partition key for a room owner."""
    return f"USER#{user_id}"


def idea_sk(created_at: str, idea_id: str) -> str:
    """Idea sort key; ideas sort by creation time."""
    return f"IDEA#{created_at}#{idea_id}"


def vote_sk(user_id: str, idea_id: str) -> str:
    """Vote-marker sort key; one per user per idea."""
    return f"VOTE#{user_id}#{idea_id}"


def comment_sk(idea_id: str, created_at: str, comment_id: str) -> str:
    """Comment sort key; groups comments by idea, oldest first."""
    return f"COMMENT#{idea_id}#{created_at}#{comment_id}"


def connection_sk(connection_id: str) -> str:
    """WebSocket connection sort key; sorts after META so board loads skip it."""
    return f"{CONNECTION_PREFIX}{connection_id}"


def connection_pk(connection_id: str) -> str:
    """Partition key of the item that maps a connection back to its room (for $disconnect)."""
    return f"CONN#{connection_id}"


def owner_room_sk(created_at: str, room_id: str) -> str:
    """GSI1 sort key for an owner's rooms, newest last."""
    return f"ROOM#{created_at}#{room_id}"
