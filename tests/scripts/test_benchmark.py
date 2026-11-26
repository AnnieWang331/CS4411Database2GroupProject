"""Tests for scripts/benchmark.py on DynamoDB Local, with tiny loads."""

import csv
import importlib.util
import json
import threading
from http.server import HTTPServer
from pathlib import Path

import pytest

from brainstorm import ideas, rooms

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmark.py"
spec = importlib.util.spec_from_file_location("benchmark", SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, "RESULTS", tmp_path)
    return tmp_path


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def test_instrumented_call_counts_requests_and_capacity(table):
    benchmark.instrument(table.meta.client)
    rec = benchmark.Recorder()
    rec.scenario, rec.students, rec.phase = "t", 1, "p"

    room = rec.measure("create_room", rooms.create_room, table, "prof", "Topic")
    rec.measure("get_room", rooms.get_room, table, "missing-room")

    created, missing = rec.rows
    assert room["room_id"]
    assert created.ok and created.requests == 1 and created.capacity_units > 0
    assert not missing.ok and missing.error == "RoomNotFoundError"


def test_conflicts_and_throttles_are_read_from_cancellation_reasons():
    stats = benchmark.CallStats()
    benchmark._current.stats = stats
    try:
        benchmark._record_response(
            parsed_response={
                "Error": {"Code": "TransactionCanceledException"},
                "CancellationReasons": [
                    {"Code": "None"},
                    {"Code": "TransactionConflict"},
                    {"Code": "ThrottlingError"},
                ],
            }
        )
        benchmark._record_response(
            parsed_response={"Error": {"Code": "ProvisionedThroughputExceededException"}}
        )
    finally:
        benchmark._current.stats = None
    assert (stats.requests, stats.tx_conflicts, stats.throttles) == (2, 1, 2)


def test_vote_without_room_check_counts_votes_in_a_closed_room(table):
    room = rooms.create_room(table, "prof", "Topic")
    idea = ideas.post_idea(table, room["room_id"], "stu", "Stu", "Idea")
    rooms.close_room(table, room["room_id"], "prof")

    benchmark.vote_without_room_check(table, room["room_id"], "stu", idea["SK"])

    board = ideas.load_board(table, room["room_id"])
    assert board["ideas"][0]["vote_count"] == 1


def test_percentile_is_nearest_rank():
    values = list(range(1, 101))
    assert benchmark.percentile(values, 50) == 50
    assert benchmark.percentile(values, 95) == 95
    assert benchmark.percentile(values, 99) == 99
    assert benchmark.percentile([7.0], 99) == 7.0


def test_run_writes_results_and_finds_no_lost_updates(dynamodb, results):
    run_id = benchmark.run(
        dynamodb.meta.client.meta.endpoint_url,
        benchmark.SCENARIOS,
        [3],
        n_rooms=2,
        load=benchmark.Load(posts=1, votes=2, comments=1),
        scan_rooms=3,
        scan_ideas=2,
        run_id="test",
    )

    out = benchmark.result_paths(run_id)
    meta = json.loads(out["run"].read_text())
    assert meta["target"] == "local" and meta["billing"] == "on-demand"
    # The run's table is deleted afterwards.
    assert meta["table"] not in dynamodb.meta.client.list_tables()["TableNames"]

    checks = rows(out["checks"])
    assert {c["scenario"] for c in checks} == {
        "hot-room",
        "many-rooms",
        "no-room-check",
        "hot-idea",
    }
    assert all(c["no_lost_updates"] == "True" for c in checks)

    ops = rows(out["ops"])
    assert all(r["ok"] == "True" for r in ops)
    hot_votes = [r for r in ops if r["scenario"] == "hot-idea" and r["op"] == "vote"]
    assert len(hot_votes) == 3

    summary = {(r["scenario"], r["op"]): r for r in rows(out["summary"])}
    query, scan = (
        summary[("query-vs-scan", "board_query")],
        summary[("query-vs-scan", "board_scan")],
    )
    assert float(scan["capacity_per_op"]) > float(query["capacity_per_op"])
    assert summary[("hot-room", "all")]["count"] == str(
        sum(1 for r in ops if r["scenario"] == "hot-room")
    )

    phases = rows(out["phases"])
    assert [p["phase"] for p in phases if p["scenario"] == "hot-room"] == [
        "setup",
        "join",
        "post",
        "vote",
        "comment",
        "reload",
    ]


def load_script(name: str):
    path = SCRIPT.parent / f"{name}.py"
    module_spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_live_times_posts_and_votes_reaching_a_socket(table, dynamodb, results):
    serve_local, live_local = load_script("serve_local"), load_script("live_local")
    endpoint = dynamodb.meta.client.meta.endpoint_url
    server = HTTPServer(("127.0.0.1", 0), serve_local.make_handler(table))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    stack = live_local.LiveStack(table.name, endpoint, port=0).start()
    try:
        run_id = benchmark.live(
            f"http://127.0.0.1:{server.server_address[1]}",
            f"ws://127.0.0.1:{stack.port}",
            samples=2,
            interval=0,
            run_id="live-test",
        )
    finally:
        stack.stop()
        server.shutdown()
        server.server_close()

    out = benchmark.result_paths(run_id)
    live_rows = rows(out["live"])
    assert [(r["op"], r["ok"]) for r in live_rows] == [("post_idea", "True"), ("vote", "True")] * 2
    assert all(float(r["event_ms"]) >= float(r["http_ms"]) for r in live_rows)
    assert json.loads(out["run"].read_text())["target"] == "local"
