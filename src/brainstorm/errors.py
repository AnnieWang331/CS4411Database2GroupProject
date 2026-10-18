"""Domain errors raised by the data layer; handlers map them to HTTP status codes."""


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
