"""Tests for scripts/ttl_demo.py on DynamoDB Local (which doesn't run TTL deletes itself)."""

import csv
import importlib.util
from datetime import timedelta
from pathlib import Path

import pytest

from brainstorm import db, keys

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ttl_demo.py"
spec = importlib.util.spec_from_file_location("ttl_demo", SCRIPT)
ttl_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ttl_demo)


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setattr(ttl_demo, "RESULTS", tmp_path)
    return tmp_path


def streams(table):
    """Streams client for the same DynamoDB Local as ``table``."""
    return db.streams_client(table.meta.client.meta.endpoint_url)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def test_start_records_every_item_with_the_rooms_ttl(table, results):
    run_id = ttl_demo.start(table, n_rooms=2, minutes=5)

    items = rows(ttl_demo.paths(run_id)["items"])
    # Per room: META, code, 2 participants, 2 ideas, 2 votes, 1 comment.
    assert len(items) == 18
    assert {i["entity_type"] for i in items} == {
        "ROOM",
        "ROOM_CODE",
        "PARTICIPANT",
        "IDEA",
        "VOTE",
        "COMMENT",
    }
    for room_id in {i["room_id"] for i in items}:
        assert len({i["expires_at"] for i in items if i["room_id"] == room_id}) == 1


def test_read_stream_returns_the_writes(table):
    ttl_demo.fill_room(table, minutes=5, n=1)

    records = ttl_demo.read_stream(streams(table), table.latest_stream_arn)

    assert sum(r["eventName"] == "INSERT" for r in records) == 9


def test_check_shows_reads_hide_expired_rooms_before_ttl_deletes_them(table, results, monkeypatch):
    run_id = ttl_demo.start(table, n_rooms=1, minutes=1)
    later = keys.utc_now() + timedelta(minutes=2)
    monkeypatch.setattr(ttl_demo.keys, "utc_now", lambda: later)

    ttl_demo.check(table, streams(table), run_id, api_url=None)

    files = ttl_demo.paths(run_id)
    [read] = rows(files["reads"])
    assert read["meta_present"] == "True"
    assert (read["get_room"], read["resolve_code"]) == ("hidden", "hidden")
    assert all(c["present"] == "True" for c in rows(files["checks"]))
    assert rows(files["deletes"]) == []
