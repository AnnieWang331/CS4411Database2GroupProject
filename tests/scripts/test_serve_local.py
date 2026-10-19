"""Tests for scripts/serve_local.py: real HTTP requests to the local server on DynamoDB Local."""

import importlib.util
import json
import threading
from http.server import HTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "serve_local.py"
spec = importlib.util.spec_from_file_location("serve_local", SCRIPT)
serve_local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve_local)


@pytest.fixture
def base_url(table):
    """Run the local server on a free port for one test and return its URL."""
    server = HTTPServer(("127.0.0.1", 0), serve_local.make_handler(table))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def send(url: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict | None]:
    """Send one request as user ``prof`` and return (status, decoded JSON body)."""
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, method=method, headers={"X-User-Id": "prof"})
    try:
        with urlopen(req) as resp:
            status, raw = resp.status, resp.read()
    except HTTPError as err:
        status, raw = err.code, err.read()
    return status, json.loads(raw) if raw else None


def test_to_event_joins_repeated_query_params():
    event = serve_local.to_event("GET", "/rooms/r1/ideas?limit=2&x=a&x=b", {"X-User-Id": "u"}, b"")
    assert event["rawPath"] == "/rooms/r1/ideas"
    assert event["queryStringParameters"] == {"limit": "2", "x": "a,b"}
    assert event["headers"] == {"x-user-id": "u"}
    assert event["body"] is None


def test_room_idea_and_vote_over_http(base_url):
    status, room = send(f"{base_url}/rooms", "POST", {"topic": "Streams"})
    assert status == 201
    rid = room["room_id"]
    status, idea = send(
        f"{base_url}/rooms/{rid}/ideas", "POST", {"display_name": "Prof", "body": "Use a GSI"}
    )
    assert status == 201
    vote_url = f"{base_url}/rooms/{rid}/ideas/{quote(idea['idea_sk'], safe='')}/vote"
    assert send(vote_url, "PUT") == (204, None)

    status, board = send(f"{base_url}/rooms/{rid}")
    assert status == 200
    assert board["ideas"][0]["vote_count"] == 1


def test_errors_come_back_as_json(base_url):
    status, body = send(f"{base_url}/codes/ZZZZZZ")
    assert (status, body["error"]) == (404, "room_not_found")
