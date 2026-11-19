"""Domain errors raised by the data layer, and how both handlers turn any error into a status."""

import logging
from dataclasses import dataclass

from botocore.exceptions import ClientError

from brainstorm.transactions import RETRYABLE_CODES, TransactionCanceledError


class BrainstormError(Exception):
    """Base class for data-layer errors."""


class RoomNotFoundError(BrainstormError):
    """The room or join code doesn't exist or has expired (404)."""


class RoomClosedError(BrainstormError):
    """The room is closed or expired, so it accepts no more writes (409)."""


class NotRoomOwnerError(BrainstormError):
    """Only the room's owner may do this (403)."""


class IdeaNotFoundError(BrainstormError):
    """The idea doesn't exist in this room (404)."""


class AlreadyVotedError(BrainstormError):
    """The user has already voted for this idea (409)."""


class NotVotedError(BrainstormError):
    """The user hasn't voted for this idea (409)."""


class CodeUnavailableError(BrainstormError):
    """No free join code was found after several attempts (503)."""


class InvalidInputError(BrainstormError):
    """A request field is missing or too long (400)."""


# Data-layer error -> (HTTP status, error code); test_api checks every subclass is listed.
ERROR_STATUS: dict[type[BrainstormError], tuple[int, str]] = {
    InvalidInputError: (400, "invalid_input"),
    NotRoomOwnerError: (403, "not_room_owner"),
    RoomNotFoundError: (404, "room_not_found"),
    IdeaNotFoundError: (404, "idea_not_found"),
    RoomClosedError: (409, "room_closed"),
    AlreadyVotedError: (409, "already_voted"),
    NotVotedError: (409, "not_voted"),
    CodeUnavailableError: (503, "code_unavailable"),
}
# DynamoDB errors that mean "too busy right now" rather than a bug.
THROTTLING_CODES = {"ProvisionedThroughputExceededException", "ThrottlingException"}


@dataclass(frozen=True)
class ErrorInfo:
    """What a handler returns and logs for an error. ``log_level`` is None when it's expected."""

    status: int
    code: str
    message: str
    log_level: int | None = None


BUSY = ErrorInfo(503, "busy", "the database is busy, please try again", logging.WARNING)
INTERNAL = ErrorInfo(500, "internal_error", "something went wrong", logging.ERROR)


def classify_error(err: Exception) -> ErrorInfo:
    """Map an exception from the data layer or DynamoDB to a status, error code and log level.

    Busy (conflicts or throttling after transact_write's retries) is a 503 logged as a warning, so
    refused requests during a burst still show up in the logs. Anything unexpected is a 500 and
    the caller should log the traceback.
    """
    if isinstance(err, BrainstormError):
        status, code = ERROR_STATUS[type(err)]
        return ErrorInfo(status, code, str(err) or code)
    if isinstance(err, TransactionCanceledError):
        return BUSY if RETRYABLE_CODES & set(err.codes) else INTERNAL
    if isinstance(err, ClientError):
        return BUSY if err.response["Error"]["Code"] in THROTTLING_CODES else INTERNAL
    return INTERNAL
