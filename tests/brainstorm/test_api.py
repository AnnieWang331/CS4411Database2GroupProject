"""Tests for the HTTP API handler, sending API Gateway events against DynamoDB Local."""

import base64
import json
from typing import Any
from urllib.parse import quote

import pytest

from brainstorm import api
from brainstorm.transactions import TransactionCanceledError


def call(
    table,
    method: str,
    path: str,
    body: Any = None,
    user: str | None = "prof",
    query: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """Send one request through the handler and return (status, decoded JSON body)."""
    event: dict[str, Any] = {
        "rawPath": path,
        "requestContext": {"http": {"method": method, "path": path}},
        "headers": {"X-User-Id": user} if user else {},
        "queryStringParameters": query,
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }
    resp = api.handle(table, event)
    assert resp["headers"]["Access-Control-Allow-Origin"] == "*"
    return resp["statusCode"], json.loads(resp["body"]) if resp["body"] else None


@pytest.fixture
def room(table) -> dict[str, Any]:
    """An open room owned by ``prof``, created through the API."""
    status, room = call(table, "POST", "/rooms", {"topic": "Indexing"})
    assert status == 201
    return room


def post_idea(table, room_id: str, text: str = "Use a GSI", user: str = "stu-1") -> dict:
    """Post an idea through the API and return it."""
    status, idea = call(
        table,
        "POST",
        f"/rooms/{room_id}/ideas",
        {"display_name": "Roah", "body": text},
        user,
    )
    assert status == 201
    return idea


def idea_path(room_id: str, idea: dict, suffix: str) -> str:
    """Build an idea route with the idea key percent-encoded, as the browser would."""
    return f"/rooms/{room_id}/ideas/{quote(idea['idea_sk'], safe='')}/{suffix}"


def test_create_room_hides_keys_and_owner_id(room):
    assert room["status"] == "open"
    assert "owner_id" not in room
    assert not {"PK", "SK", "GSI1PK", "GSI1SK"} & room.keys()
    assert isinstance(room["expires_at"], int)


def test_code_lookup_and_my_rooms(table, room):
    status, found = call(table, "GET", f"/codes/{room['code'].lower()}", user=None)
    assert (status, found["room_id"]) == (200, room["room_id"])
    status, mine = call(table, "GET", "/my-rooms")
    assert [r["room_id"] for r in mine["rooms"]] == [room["room_id"]]


def test_unknown_code_is_404(table):
    status, body = call(table, "GET", "/codes/ZZZZZZ")
    assert (status, body["error"]) == (404, "room_not_found")


def test_full_board_flow(table, room):
    rid = room["room_id"]
    assert call(table, "POST", f"/rooms/{rid}/join", {"display_name": "Roah"}, "stu-1")[0] == 200
    idea = post_idea(table, rid)
    assert idea["idea_sk"].startswith("IDEA#")
    assert call(table, "PUT", idea_path(rid, idea, "vote"), user="stu-2") == (204, None)
    status, comment = call(
        table,
        "POST",
        idea_path(rid, idea, "comments"),
        {"display_name": "Sachin", "body": "Agreed"},
        "stu-2",
    )
    assert status == 201

    status, board = call(table, "GET", f"/rooms/{rid}", user=None, query={"comments": "true"})
    assert status == 200
    assert board["ideas"][0]["vote_count"] == 1
    assert board["ideas"][0]["comment_count"] == 1
    assert board["comments"][idea["idea_id"]][0]["comment_id"] == comment["comment_id"]

    status, votes = call(table, "GET", f"/rooms/{rid}/my-votes", user="stu-2")
    assert votes == {"idea_ids": [idea["idea_id"]]}
    status, people = call(table, "GET", f"/rooms/{rid}/participants", user=None)
    assert [p["display_name"] for p in people["participants"]] == ["Roah"]
    status, comments = call(table, "GET", idea_path(rid, idea, "comments"), user=None)
    assert [c["body"] for c in comments["comments"]] == ["Agreed"]


def test_vote_twice_then_unvote(table, room):
    rid = room["room_id"]
    idea = post_idea(table, rid)
    path = idea_path(rid, idea, "vote")
    assert call(table, "PUT", path, user="stu-2")[0] == 204
    assert call(table, "PUT", path, user="stu-2")[1]["error"] == "already_voted"
    assert call(table, "DELETE", path, user="stu-2")[0] == 204
    status, body = call(table, "DELETE", path, user="stu-2")
    assert (status, body["error"]) == (409, "not_voted")


def test_vote_on_missing_idea_is_404(table, room):
    missing = {"idea_sk": "IDEA#2026-01-01T00:00:00.000Z#nope"}
    status, body = call(table, "PUT", idea_path(room["room_id"], missing, "vote"))
    assert (status, body["error"]) == (404, "idea_not_found")


def test_only_owner_can_close_and_closed_room_rejects_posts(table, room):
    rid = room["room_id"]
    status, body = call(table, "POST", f"/rooms/{rid}/close", user="stu-1")
    assert (status, body["error"]) == (403, "not_room_owner")
    assert call(table, "POST", f"/rooms/{rid}/close") == (204, None)
    status, body = call(
        table,
        "POST",
        f"/rooms/{rid}/ideas",
        {"display_name": "Roah", "body": "Late"},
        "stu-1",
    )
    assert (status, body["error"]) == (409, "room_closed")


def test_ideas_pagination_with_cursor(table, room):
    rid = room["room_id"]
    posted = [post_idea(table, rid, f"Idea {n}")["idea_id"] for n in range(3)]
    status, first = call(table, "GET", f"/rooms/{rid}/ideas", query={"limit": "2"})
    assert status == 200 and len(first["ideas"]) == 2 and first["cursor"]
    status, second = call(
        table,
        "GET",
        f"/rooms/{rid}/ideas",
        query={"limit": "2", "cursor": first["cursor"]},
    )
    assert second["cursor"] is None
    # Ideas posted in the same millisecond sort by id, so compare without order.
    seen = [i["idea_id"] for i in first["ideas"] + second["ideas"]]
    assert sorted(seen) == sorted(posted)


def test_cursor_from_another_room_is_rejected(table, room):
    other = call(table, "POST", "/rooms", {"topic": "Other"})[1]
    for n in range(2):
        post_idea(table, other["room_id"], f"Idea {n}")
    cursor = call(table, "GET", f"/rooms/{other['room_id']}/ideas", query={"limit": "1"})[1][
        "cursor"
    ]
    status, body = call(table, "GET", f"/rooms/{room['room_id']}/ideas", query={"cursor": cursor})
    assert (status, body["error"]) == (400, "invalid_input")


@pytest.mark.parametrize(
    "start_key",
    [
        ["not", "a", "dict"],
        {"PK": "ROOM#{rid}", "SK": "IDEA#x", "extra": "1"},
        {"PK": "ROOM#{rid}", "SK": "USER#prof"},
        {"PK": "ROOM#{rid}", "SK": 5},
    ],
)
def test_forged_cursor_is_400(table, room, start_key):
    raw = json.dumps(start_key).replace("{rid}", room["room_id"])
    cursor = base64.urlsafe_b64encode(raw.encode()).decode()
    status, body = call(table, "GET", f"/rooms/{room['room_id']}/ideas", query={"cursor": cursor})
    assert (status, body["error"]) == (400, "invalid_input")


@pytest.mark.parametrize("limit", ["0", "101", "abc"])
def test_bad_limit_is_400(table, room, limit):
    status, _ = call(table, "GET", f"/rooms/{room['room_id']}/ideas", query={"limit": limit})
    assert status == 400


@pytest.mark.parametrize("user", [None, "", "a#b", "x" * 65])
def test_writes_need_a_valid_user_id(table, user):
    status, body = call(table, "POST", "/rooms", {"topic": "T"}, user=user)
    assert (status, body["error"]) == (401, "missing_user")


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        [1, 2],
        {"display_name": "Roah"},
        {"display_name": "x" * 51, "body": "Hi"},
    ],
)
def test_bad_idea_bodies_are_400(table, room, body):
    raw = body if isinstance(body, str) else json.dumps(body)
    event = {
        "rawPath": f"/rooms/{room['room_id']}/ideas",
        "requestContext": {"http": {"method": "POST"}},
        "headers": {"x-user-id": "stu-1"},
        "body": raw,
    }
    resp = api.handle(table, event)
    assert resp["statusCode"] == 400
    assert json.loads(resp["body"])["error"] == "invalid_input"


def test_base64_body_is_decoded(table):
    event = {
        "rawPath": "/rooms",
        "requestContext": {"http": {"method": "POST"}},
        "headers": {"x-user-id": "prof"},
        "body": base64.b64encode(json.dumps({"topic": "Encoded"}).encode()).decode(),
        "isBase64Encoded": True,
    }
    resp = api.handle(table, event)
    assert resp["statusCode"] == 201
    assert json.loads(resp["body"])["topic"] == "Encoded"


def test_bad_base64_body_is_400(table):
    event = {
        "rawPath": "/rooms",
        "requestContext": {"http": {"method": "POST"}},
        "headers": {"x-user-id": "prof"},
        "body": "%%% not base64",
        "isBase64Encoded": True,
    }
    resp = api.handle(table, event)
    assert resp["statusCode"] == 400


def test_unknown_route_and_options(table):
    assert call(table, "GET", "/nope")[1]["error"] == "not_found"
    assert call(table, "PATCH", "/rooms")[0] == 404
    assert call(table, "OPTIONS", "/rooms")[0] == 204


def test_persistent_conflict_is_503(table, room, monkeypatch):
    def always_conflict(*args, **kwargs):
        raise TransactionCanceledError(["None", "TransactionConflict"])

    monkeypatch.setattr(api.ideas, "post_idea", always_conflict)
    status, body = call(
        table,
        "POST",
        f"/rooms/{room['room_id']}/ideas",
        {"display_name": "R", "body": "x"},
    )
    assert (status, body["error"]) == (503, "busy")


def test_unexpected_error_is_500_without_details(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(api, "_table", object())
    monkeypatch.setattr(api.rooms, "list_owner_rooms", boom)
    event = {
        "rawPath": "/my-rooms",
        "requestContext": {"http": {"method": "GET"}},
        "headers": {"x-user-id": "prof"},
    }
    resp = api.lambda_handler(event, None)
    assert resp["statusCode"] == 500
    assert "secret" not in resp["body"]


def test_every_brainstorm_error_has_a_status():
    assert set(api.BrainstormError.__subclasses__()) <= api.ERROR_STATUS.keys()


def test_handle_turns_unexpected_errors_into_500(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(api.rooms, "list_owner_rooms", boom)
    status, body = call(object(), "GET", "/my-rooms")
    assert (status, body["error"]) == (500, "internal_error")
    assert "secret" not in body["message"]
