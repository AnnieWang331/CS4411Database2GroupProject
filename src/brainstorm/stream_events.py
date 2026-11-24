"""Turn DynamoDB Streams records into the live-update events sent over the WebSocket.

This is a pure mapping with no AWS calls: the stream Lambda hands each record to ``to_event`` and
sends whatever comes back to the room's connections. Which changes become which events is in
docs/data-model.md section 6; the event shapes are in docs/api.md.

Records from one transaction can arrive out of order or twice, so every event carries absolute
values (the new ``vote_count``, not a +1) and clients apply each one on its own.
"""

from decimal import Decimal
from typing import Any

from boto3.dynamodb.types import TypeDeserializer

from brainstorm import keys
from brainstorm.api import public

# TTL deletes are made by the DynamoDB service itself, not by our code.
TTL_PRINCIPAL = "dynamodb.amazonaws.com"


class _Deserializer(TypeDeserializer):
    """Like boto3's deserializer, but numbers come out as int/float so events are JSON-ready."""

    def _deserialize_n(self, value: str) -> int | float:
        number = Decimal(value)
        return int(number) if number == number.to_integral_value() else float(number)


_deserializer = _Deserializer()


def _image(record: dict[str, Any], name: str) -> dict[str, Any]:
    """Return ``NewImage``/``OldImage`` as plain Python values (empty if the record has none)."""
    raw = record.get("dynamodb", {}).get(name) or {}
    return {k: _deserializer.deserialize(v) for k, v in raw.items()}


def from_get_records(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a record from the Streams ``GetRecords`` API to the shape Lambda delivers.

    The two differ: ``GetRecords`` (through boto3) spells the identity ``{"Type", "PrincipalId"}``
    and gives ``ApproximateCreationDateTime`` as a datetime, while Lambda sends
    ``{"type", "principalId"}`` and epoch seconds. Code that polls a stream itself (the TTL demo,
    the local stack) converts first, so ``to_event`` only has to handle Lambda's shape.
    """
    record = {**record, "dynamodb": dict(record.get("dynamodb", {}))}
    identity = record.get("userIdentity")
    if identity:
        record["userIdentity"] = {
            "type": identity.get("Type", identity.get("type")),
            "principalId": identity.get("PrincipalId", identity.get("principalId")),
        }
    created = record["dynamodb"].get("ApproximateCreationDateTime")
    if hasattr(created, "timestamp"):
        record["dynamodb"]["ApproximateCreationDateTime"] = int(created.timestamp())
    return record


def is_ttl_delete(record: dict[str, Any]) -> bool:
    """Whether the record is TTL removing an expired item."""
    identity = record.get("userIdentity") or {}
    return (
        record.get("eventName") == "REMOVE"
        and identity.get("type") == "Service"
        and identity.get("principalId") == TTL_PRINCIPAL
    )


def to_event(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return the event to broadcast for one stream record, or ``None`` to send nothing."""
    name = record.get("eventName")
    new = _image(record, "NewImage")
    old = _image(record, "OldImage")
    item = new or old
    room_id = keys.room_id_from_pk(item.get("PK", ""))
    if room_id is None:  # join codes and connection lookups live outside room partitions
        return None
    entity = item.get("entity_type")

    if entity == "IDEA":
        if name == "INSERT":
            return {"type": "idea_added", "room_id": room_id, "idea": public(new)}
        if name == "MODIFY" and new.get("vote_count") != old.get("vote_count"):
            return {
                "type": "vote_count_changed",
                "room_id": room_id,
                "idea_id": new["idea_id"],
                "idea_sk": new["SK"],
                "vote_count": new["vote_count"],
            }
        # A comment_count change is skipped: the comment's own insert carries the data.
        return None
    if entity == "COMMENT" and name == "INSERT":
        return {"type": "comment_added", "room_id": room_id, "comment": public(new)}
    if entity == "PARTICIPANT" and name == "INSERT":
        return {"type": "participant_joined", "room_id": room_id, "participant": public(new)}
    if entity == "ROOM":
        # Only the status matters: closing also sets closed_at in the same write.
        if name == "MODIFY" and old.get("status") == "open" and new.get("status") == "closed":
            return {"type": "room_closed", "room_id": room_id, "closed_at": new.get("closed_at")}
        # Sent even for a room that was already closed, so its connections get cleaned up.
        if is_ttl_delete(record):
            return {"type": "room_expired", "room_id": room_id}
    return None
