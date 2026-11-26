"""Benchmark the brainstorm board under classroom load (issue #11).

Usage (global options such as --results go before the command):
  python scripts/benchmark.py run [--scenarios LIST] [--students 30,100,300] [--provisioned]
         [--endpoint-url URL] [--keep-table]

``run`` creates its own table (``bench-<RUN_ID>``, on-demand unless ``--provisioned``), so it
never touches the demo table, and deletes it afterwards unless ``--keep-table``. Every student is
a thread with its own boto3 client. Each operation calls the same data-layer function the API
does, and botocore event hooks count, per operation, the HTTP attempts, transaction conflicts,
throttles and consumed capacity (``ReturnConsumedCapacity=TOTAL`` is added to every request).

Scenarios (``--scenarios``, comma-separated, default all):

- ``hot-room``: every student in one room (one partition). Phases, each started together: join
  (resolve code, join, load board), post, vote, comment, reload the board.
- ``many-rooms``: the same students and operations spread over ``--rooms`` rooms.
- ``no-room-check``: ``hot-room``, but votes skip the room ``ConditionCheck`` (open question 3 in
  docs/data-model.md). Benchmark only; the app always checks the room.
- ``hot-idea``: everyone votes on the same idea at the same moment.
- ``query-vs-scan``: loading one board with a Query versus a Scan with a filter, on a table
  holding ``--scan-rooms`` rooms.

After each scenario the vote and comment counters are checked against the items (no lost
updates). Results go to ``benchmarks/results/bench-<RUN_ID>-*.csv`` plus ``-run.json``.

DynamoDB Local doesn't model partitions, throttling or real latency: its numbers only show how
the code behaves, and hot-partition and capacity results must come from AWS.
"""

import argparse
import csv
import json
import os
import platform
import random
import statistics
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import BotoCoreError, ClientError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from brainstorm import db, ideas, keys, rooms, schema  # noqa: E402 - needs the sys.path entry
from brainstorm.errors import BrainstormError  # noqa: E402
from brainstorm.transactions import TransactionCanceledError, transact_write  # noqa: E402

RESULTS = ROOT / "benchmarks" / "results"
SCENARIOS = ["hot-room", "many-rooms", "no-room-check", "hot-idea", "query-vs-scan"]
DEFAULT_STUDENTS = [30, 100, 300]

# Requests that accept ReturnConsumedCapacity.
CAPACITY_OPS = [
    "GetItem",
    "Query",
    "Scan",
    "PutItem",
    "UpdateItem",
    "DeleteItem",
    "TransactWriteItems",
    "BatchWriteItem",
]
THROTTLE_CODES = {
    "ProvisionedThroughputExceededException",
    "ThrottlingException",
    "RequestLimitExceeded",
}
THROTTLE_REASONS = {"ProvisionedThroughputExceeded", "ThrottlingError"}

OP_FIELDS = [
    "scenario",
    "students",
    "phase",
    "op",
    "start_s",
    "latency_ms",
    "ok",
    "error",
    "requests",
    "tx_conflicts",
    "throttles",
    "capacity_units",
    "items_read",
]
PHASE_FIELDS = ["scenario", "students", "phase", "wall_s", "ops", "ok", "ops_per_s", "client_cpu"]
SUMMARY_FIELDS = [
    "scenario",
    "students",
    "op",
    "count",
    "ok",
    "errors",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "max_ms",
    "ok_per_s",
    "retried_ops",
    "tx_conflicts",
    "throttles",
    "capacity_units",
    "capacity_per_op",
    "capacity_per_s",
]
CHECK_FIELDS = [
    "scenario",
    "students",
    "votes_ok",
    "vote_markers",
    "vote_count_sum",
    "comments_ok",
    "comment_items",
    "comment_count_sum",
    "no_lost_updates",
]


# --- Per-operation instrumentation -------------------------------------------------------------


@dataclass
class CallStats:
    """What one data-layer call cost, collected by the botocore hooks on its thread."""

    requests: int = 0
    tx_conflicts: int = 0
    throttles: int = 0
    capacity_units: float = 0.0
    items_read: int = 0


_current = threading.local()


def _ask_for_capacity(params: dict[str, Any], **_: Any) -> None:
    params.setdefault("ReturnConsumedCapacity", "TOTAL")


def _record_response(parsed_response: dict[str, Any] | None = None, **_: Any) -> None:
    """Runs after every HTTP attempt, including the ones botocore retries itself."""
    stats: CallStats | None = getattr(_current, "stats", None)
    if stats is None:
        return
    stats.requests += 1
    if not parsed_response:
        return
    code = parsed_response.get("Error", {}).get("Code")
    if code in THROTTLE_CODES:
        stats.throttles += 1
    for reason in parsed_response.get("CancellationReasons", []):
        if reason.get("Code") == "TransactionConflict":
            stats.tx_conflicts += 1
        elif reason.get("Code") in THROTTLE_REASONS:
            stats.throttles += 1
    consumed = parsed_response.get("ConsumedCapacity", [])
    for entry in consumed if isinstance(consumed, list) else [consumed]:
        stats.capacity_units += float(entry.get("CapacityUnits", 0))
    stats.items_read += int(parsed_response.get("ScannedCount", 0))


def instrument(client) -> None:
    """Register the hooks on one boto3 client."""
    events = client.meta.events
    for op in CAPACITY_OPS:
        events.register(f"provide-client-params.dynamodb.{op}", _ask_for_capacity)
    events.register("response-received.dynamodb.*", _record_response)


@dataclass
class OpResult:
    scenario: str
    students: int
    phase: str
    op: str
    start_s: float
    latency_ms: float
    ok: bool
    error: str
    requests: int
    tx_conflicts: int
    throttles: int
    capacity_units: float
    items_read: int


def error_name(err: Exception) -> str:
    """A short label for a failed operation."""
    if isinstance(err, TransactionCanceledError):
        return "TransactionCanceled:" + "+".join(sorted({c for c in err.codes if c != "None"}))
    if isinstance(err, ClientError):
        return err.response["Error"]["Code"]
    return type(err).__name__


class Recorder:
    """Collects ``OpResult`` rows from all worker threads."""

    def __init__(self) -> None:
        self.rows: list[OpResult] = []
        self.phases: list[dict[str, Any]] = []
        self.checks: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self.scenario = ""
        self.students = 0
        self.phase = ""
        self.origin = time.perf_counter()

    def measure(self, op: str, fn: Callable[..., Any], *args: Any) -> Any:
        """Run ``fn(*args)``, record its latency and cost, and return its result (None on error)."""
        stats = CallStats()
        _current.stats = stats
        error, result = "", None
        start = time.perf_counter()
        try:
            result = fn(*args)
        except (BrainstormError, TransactionCanceledError, ClientError) as err:
            error = error_name(err)
        finally:
            latency = time.perf_counter() - start
            _current.stats = None
        row = OpResult(
            scenario=self.scenario,
            students=self.students,
            phase=self.phase,
            op=op,
            start_s=round(start - self.origin, 4),
            latency_ms=round(latency * 1000, 2),
            ok=not error,
            error=error,
            requests=stats.requests,
            tx_conflicts=stats.tx_conflicts,
            throttles=stats.throttles,
            capacity_units=round(stats.capacity_units, 2),
            items_read=stats.items_read,
        )
        with self._lock:
            self.rows.append(row)
        return result


class Workers:
    """One boto3 resource (and so one client and connection pool) per simulated student.

    boto3 resources aren't thread-safe, so each thread gets its own; they're created one at a
    time because creating them from one session isn't thread-safe either.
    """

    def __init__(self, endpoint: str | None, table_name: str) -> None:
        self.endpoint = endpoint
        self.table_name = table_name
        self.tables: list[Any] = []

    def ensure(self, n: int) -> None:
        new = []
        while len(self.tables) < n:
            resource = db.resource(self.endpoint)
            instrument(resource.meta.client)
            table = resource.Table(self.table_name)
            self.tables.append(table)
            new.append(table)
        # Open each connection before measuring, so no operation pays for the TLS handshake.
        run_parallel([lambda t=t: t.get_item(Key={"PK": "WARMUP", "SK": "WARMUP"}) for t in new])


def run_parallel(tasks: list[Callable[[], Any]], barrier: bool = False) -> None:
    """Run each task on its own thread and wait for all; with ``barrier`` they start together."""
    if not tasks:
        return
    gate = threading.Barrier(len(tasks)) if barrier else None
    errors: list[BaseException] = []

    def wrap(task: Callable[[], Any]) -> None:
        try:
            if gate:
                gate.wait()
            task()
        except BaseException as err:  # surfaced below; a dead thread would hide it
            errors.append(err)

    threads = [threading.Thread(target=wrap, args=(t,)) for t in tasks]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        raise errors[0]


def phase(rec: Recorder, name: str, tasks: list[Callable[[], Any]]) -> None:
    """Run one phase: every task starts at once; records wall time and client CPU use."""
    rec.phase = name
    before = len(rec.rows)
    cpu0, wall0 = time.process_time(), time.perf_counter()
    run_parallel(tasks, barrier=True)
    wall = time.perf_counter() - wall0
    cpu = time.process_time() - cpu0
    rows = rec.rows[before:]
    ok = sum(r.ok for r in rows)
    rec.phases.append(
        {
            "scenario": rec.scenario,
            "students": rec.students,
            "phase": name,
            "wall_s": round(wall, 3),
            "ops": len(rows),
            "ok": ok,
            "ops_per_s": round(ok / wall, 1) if wall else 0,
            # Cores' worth of CPU this process used. Near 1.0 means the client (Python's GIL),
            # not DynamoDB, may be what limits throughput, so read latencies with care.
            "client_cpu": round(cpu / wall, 2) if wall else 0,
        }
    )


# --- Scenario building blocks ------------------------------------------------------------------


@dataclass
class Student:
    index: int
    user_id: str
    name: str
    room: dict[str, Any]
    rng: random.Random
    posted: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Load:
    """What each student does in the classroom scenarios."""

    posts: int = 2
    votes: int = 5
    comments: int = 1


def vote_without_room_check(table, room_id: str, user_id: str, idea_sk: str) -> None:
    """``ideas.vote`` minus the room ConditionCheck (open question 3). Benchmark only.

    Still reads the room first, like ``ideas.vote``, so the only difference is that the
    transaction no longer touches the room's META item.
    """
    idea_id = ideas.idea_id_from_sk(idea_sk)
    room = rooms.get_room(table, room_id)
    marker = {
        "PK": keys.room_pk(room_id),
        "SK": keys.vote_sk(user_id, idea_id),
        "entity_type": "VOTE",
        "user_id": user_id,
        "idea_id": idea_id,
        "idea_sk": idea_sk,
        "created_at": keys.iso(keys.utc_now()),
        "expires_at": room["expires_at"],
    }
    transact_write(
        table,
        [
            {"Put": {"Item": marker, "ConditionExpression": "attribute_not_exists(PK)"}},
            {
                "Update": {
                    "Key": {"PK": keys.room_pk(room_id), "SK": idea_sk},
                    "UpdateExpression": "ADD vote_count :one",
                    "ConditionExpression": "attribute_exists(PK)",
                    "ExpressionAttributeValues": {":one": 1},
                }
            },
        ],
    )


def make_rooms(rec: Recorder, workers: Workers, n_rooms: int, label: str) -> list[dict[str, Any]]:
    """Create ``n_rooms`` rooms in parallel (the 'setup' phase) and return their META items."""
    workers.ensure(n_rooms)
    made: list[dict[str, Any] | None] = [None] * n_rooms

    def create(i: int) -> None:
        made[i] = rec.measure(
            "create_room", rooms.create_room, workers.tables[i], f"prof-{label}-{i}", "Benchmark"
        )

    phase(rec, "setup", [lambda i=i: create(i) for i in range(n_rooms)])
    if any(room is None for room in made):
        raise RuntimeError("could not create the benchmark rooms")
    return made  # type: ignore[return-value]


def make_students(rec: Recorder, room_list: list[dict[str, Any]], seed: int) -> list[Student]:
    return [
        Student(
            index=i,
            user_id=f"stu-{rec.scenario}-{rec.students}-{i}",
            name=f"Student {i}",
            room=room_list[i % len(room_list)],
            rng=random.Random(seed * 100_003 + i),
        )
        for i in range(rec.students)
    ]


def join_phase(rec: Recorder, workers: Workers, students: list[Student]) -> None:
    def join(s: Student) -> None:
        table = workers.tables[s.index]
        rec.measure("resolve_code", rooms.resolve_code, table, s.room["code"])
        rec.measure("join_room", rooms.join_room, table, s.room["room_id"], s.user_id, s.name)
        rec.measure("load_board", ideas.load_board, table, s.room["room_id"], True)

    phase(rec, "join", [lambda s=s: join(s) for s in students])


def classroom(
    rec: Recorder,
    workers: Workers,
    n_rooms: int,
    load: Load,
    seed: int,
    vote_fn: Callable[..., None] = ideas.vote,
) -> None:
    """Join, post, vote, comment and reload, each phase started by all students together."""
    workers.ensure(rec.students)
    room_list = make_rooms(rec, workers, n_rooms, f"{rec.scenario}-{rec.students}")
    students = make_students(rec, room_list, seed)
    join_phase(rec, workers, students)

    def post(s: Student) -> None:
        for n in range(load.posts):
            idea = rec.measure(
                "post_idea",
                ideas.post_idea,
                workers.tables[s.index],
                s.room["room_id"],
                s.user_id,
                s.name,
                f"Idea {n} from student {s.index}",
            )
            if idea:
                s.posted.append(idea)

    phase(rec, "post", [lambda s=s: post(s) for s in students])

    # Everyone sees the ideas of their own room (from the live board), and votes on some.
    by_room: dict[str, list[str]] = {}
    for s in students:
        by_room.setdefault(s.room["room_id"], []).extend(i["SK"] for i in s.posted)

    def vote(s: Student) -> None:
        pool = by_room[s.room["room_id"]]
        for idea_sk in s.rng.sample(pool, min(load.votes, len(pool))):
            rec.measure(
                "vote", vote_fn, workers.tables[s.index], s.room["room_id"], s.user_id, idea_sk
            )

    phase(rec, "vote", [lambda s=s: vote(s) for s in students])

    def comment(s: Student) -> None:
        pool = by_room[s.room["room_id"]]
        for n in range(load.comments):
            rec.measure(
                "comment",
                ideas.add_comment,
                workers.tables[s.index],
                s.room["room_id"],
                s.rng.choice(pool),
                s.user_id,
                s.name,
                f"Comment {n} from student {s.index}",
            )

    phase(rec, "comment", [lambda s=s: comment(s) for s in students])

    def reload(s: Student) -> None:
        rec.measure(
            "load_board", ideas.load_board, workers.tables[s.index], s.room["room_id"], True
        )

    phase(rec, "reload", [lambda s=s: reload(s) for s in students])
    check_counters(rec, workers.tables[0], room_list)


def hot_idea(rec: Recorder, workers: Workers, seed: int) -> None:
    """Everyone votes for the same idea at the same moment."""
    workers.ensure(rec.students)
    [room] = make_rooms(rec, workers, 1, f"{rec.scenario}-{rec.students}")
    students = make_students(rec, [room], seed)
    join_phase(rec, workers, students)
    rec.phase = "post"
    idea = rec.measure(
        "post_idea", ideas.post_idea, workers.tables[0], room["room_id"], "prof", "Prof", "Hot idea"
    )
    if idea is None:
        raise RuntimeError("could not post the hot idea")

    def vote(s: Student) -> None:
        rec.measure(
            "vote", ideas.vote, workers.tables[s.index], room["room_id"], s.user_id, idea["SK"]
        )

    phase(rec, "vote", [lambda s=s: vote(s) for s in students])
    check_counters(rec, workers.tables[0], [room])


def check_counters(rec: Recorder, table, room_list: list[dict[str, Any]]) -> None:
    """Compare the counters with the vote and comment items they count (no lost updates)."""
    markers = comment_items = vote_sum = comment_sum = 0
    for room in room_list:
        items = rooms.query_all(
            table,
            KeyConditionExpression=Key("PK").eq(keys.room_pk(room["room_id"])),
            ConsistentRead=True,
        )
        for item in items:
            kind = item["entity_type"]
            markers += kind == "VOTE"
            comment_items += kind == "COMMENT"
            if kind == "IDEA":
                vote_sum += int(item["vote_count"])
                comment_sum += int(item["comment_count"])
    mine = [r for r in rec.rows if r.scenario == rec.scenario and r.students == rec.students]
    votes_ok = sum(r.ok for r in mine if r.op == "vote")
    comments_ok = sum(r.ok for r in mine if r.op == "comment")
    rec.checks.append(
        {
            "scenario": rec.scenario,
            "students": rec.students,
            "votes_ok": votes_ok,
            "vote_markers": markers,
            "vote_count_sum": vote_sum,
            "comments_ok": comments_ok,
            "comment_items": comment_items,
            "comment_count_sum": comment_sum,
            "no_lost_updates": votes_ok == markers == vote_sum
            and comments_ok == comment_items == comment_sum,
        }
    )


def query_vs_scan(rec: Recorder, workers: Workers, n_rooms: int, ideas_per_room: int, seed: int):
    """Load a board with one Query vs a Scan of the whole table filtered to that room."""
    workers.ensure(1)
    table = workers.tables[0]
    expires_at = keys.epoch(keys.utc_now() + rooms.DEFAULT_TTL)
    room_ids = [keys.new_id() for _ in range(n_rooms)]
    with table.batch_writer() as batch:  # seeding only, not measured
        for room_id in room_ids:
            batch.put_item(
                Item={
                    "PK": keys.room_pk(room_id),
                    "SK": keys.META,
                    "entity_type": "ROOM",
                    "room_id": room_id,
                    "code": "SCAN00",
                    "topic": "Scan benchmark",
                    "status": rooms.OPEN,
                    "owner_id": "prof-scan",
                    "created_at": keys.iso(keys.utc_now()),
                    "expires_at": expires_at,
                }
            )
            for n in range(ideas_per_room):
                created_at, idea_id = keys.iso(keys.utc_now()), keys.new_id()
                batch.put_item(
                    Item={
                        "PK": keys.room_pk(room_id),
                        "SK": keys.idea_sk(created_at, idea_id),
                        "entity_type": "IDEA",
                        "idea_id": idea_id,
                        "author_id": f"stu-scan-{n}",
                        "author_name": f"Student {n}",
                        "body": f"Idea {n} for the scan benchmark, about as long as a real one.",
                        "vote_count": 0,
                        "comment_count": 0,
                        "created_at": created_at,
                        "expires_at": expires_at,
                    }
                )

    def scan_board(room_id: str) -> list[dict[str, Any]]:
        # The anti-pattern the app never uses: read every item in the table, keep one room's.
        items, kwargs = [], {"FilterExpression": Attr("PK").eq(keys.room_pk(room_id))}
        while True:
            page = table.scan(**kwargs)
            items.extend(page["Items"])
            if "LastEvaluatedKey" not in page:
                return items
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    rng = random.Random(seed)
    rec.phase = "read"
    for room_id in rng.sample(room_ids, min(20, n_rooms)):
        rec.measure("board_query", ideas.load_board, table, room_id)
        rec.measure("board_scan", scan_board, room_id)


# --- Results -----------------------------------------------------------------------------------


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (no interpolation, so it is always an observed latency)."""
    ordered = sorted(values)
    rank = max(1, round(pct / 100 * len(ordered) + 0.5 - 1e-9))
    return ordered[min(rank, len(ordered)) - 1]


def summarize(rec: Recorder) -> list[dict[str, Any]]:
    """One row per scenario, size and operation, plus an ``all`` row per scenario and size."""
    walls = {(p["scenario"], p["students"], p["phase"]): p["wall_s"] for p in rec.phases}
    groups: dict[tuple[str, int, str], list[OpResult]] = {}
    for row in rec.rows:
        groups.setdefault((row.scenario, row.students, row.op), []).append(row)
        groups.setdefault((row.scenario, row.students, "all"), []).append(row)
    summary = []
    # Keep run order (scenario by scenario, ops in the order they ran), with each "all" last.
    order = sorted(groups, key=lambda k: (SCENARIOS.index(k[0]), k[1], k[2] == "all"))
    for scenario, students, op in order:
        rows = groups[(scenario, students, op)]
        latencies = [r.latency_ms for r in rows if r.ok] or [0.0]
        wall = sum(walls.get((scenario, students, ph), 0) for ph in sorted({r.phase for r in rows}))
        if not wall:  # sequential ops (query-vs-scan): time spent in them
            wall = sum(r.latency_ms for r in rows) / 1000
        ok = sum(r.ok for r in rows)
        capacity = sum(r.capacity_units for r in rows)
        summary.append(
            {
                "scenario": scenario,
                "students": students,
                "op": op,
                "count": len(rows),
                "ok": ok,
                "errors": len(rows) - ok,
                "p50_ms": round(statistics.median(latencies), 1),
                "p95_ms": percentile(latencies, 95),
                "p99_ms": percentile(latencies, 99),
                "max_ms": max(latencies),
                "ok_per_s": round(ok / wall, 1) if wall else 0,
                "retried_ops": sum(r.tx_conflicts > 0 or r.throttles > 0 for r in rows),
                "tx_conflicts": sum(r.tx_conflicts for r in rows),
                "throttles": sum(r.throttles for r in rows),
                "capacity_units": round(capacity, 1),
                "capacity_per_op": round(capacity / len(rows), 2),
                "capacity_per_s": round(capacity / wall, 1) if wall else 0,
            }
        )
    return summary


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def result_paths(run_id: str) -> dict[str, Path]:
    return {
        name: RESULTS / f"bench-{run_id}-{name}.{ext}"
        for name, ext in [
            ("run", "json"),
            ("ops", "csv"),
            ("phases", "csv"),
            ("summary", "csv"),
            ("checks", "csv"),
        ]
    }


def save(run_id: str, rec: Recorder, meta: dict[str, Any]) -> dict[str, Path]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = result_paths(run_id)
    out["run"].write_text(json.dumps(meta, indent=2) + "\n")
    write_csv(out["ops"], OP_FIELDS, [asdict(r) for r in rec.rows])
    write_csv(out["phases"], PHASE_FIELDS, rec.phases)
    write_csv(out["summary"], SUMMARY_FIELDS, summarize(rec))
    write_csv(out["checks"], CHECK_FIELDS, rec.checks)
    return out


# --- Commands ----------------------------------------------------------------------------------


def run(
    endpoint: str | None,
    scenarios: list[str],
    student_counts: list[int],
    provisioned: bool = False,
    n_rooms: int = 10,
    load: Load | None = None,
    scan_rooms: int = 100,
    scan_ideas: int = 30,
    seed: int = 4411,
    keep_table: bool = False,
    run_id: str | None = None,
) -> str:
    """Run the scenarios on a new table and save the results; returns the run id."""
    load = load or Load()
    run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    table_name = f"bench-{run_id}"
    dynamodb = db.resource(endpoint)
    table = schema.create_table(dynamodb, table_name, provisioned=provisioned)
    meta: dict[str, Any] = {
        "run_id": run_id,
        "target": "local" if endpoint else "aws",
        "endpoint": endpoint,
        "region": dynamodb.meta.client.meta.region_name,
        "table": table_name,
        "billing": "provisioned" if provisioned else "on-demand",
        "provisioned_units": (
            {"table": schema.TABLE_UNITS, "gsi1": schema.GSI1_UNITS} if provisioned else None
        ),
        "scenarios": scenarios,
        "students": student_counts,
        "rooms": n_rooms,
        "load": asdict(load),
        "scan": {"rooms": scan_rooms, "ideas_per_room": scan_ideas},
        "seed": seed,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "boto3": boto3.__version__,
        "client": f"{platform.system()} {platform.machine()}, {os.cpu_count()} CPUs",
    }
    rec = Recorder()
    workers = Workers(endpoint, table_name)
    try:
        for students in student_counts:
            for scenario in [s for s in scenarios if s != "query-vs-scan"]:
                rec.scenario, rec.students = scenario, students
                print(f"{scenario}, {students} students ...", flush=True)
                if scenario == "hot-room":
                    classroom(rec, workers, 1, load, seed)
                elif scenario == "many-rooms":
                    classroom(rec, workers, min(n_rooms, students), load, seed)
                elif scenario == "no-room-check":
                    classroom(rec, workers, 1, load, seed, vote_fn=vote_without_room_check)
                elif scenario == "hot-idea":
                    hot_idea(rec, workers, seed)
        if "query-vs-scan" in scenarios:
            rec.scenario, rec.students = "query-vs-scan", 1
            print(f"query-vs-scan, {scan_rooms} rooms x {scan_ideas} ideas ...", flush=True)
            query_vs_scan(rec, workers, scan_rooms, scan_ideas, seed)
    finally:
        meta["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        meta["table_kept"] = keep_table
        save(run_id, rec, meta)
        if not keep_table:
            table.delete()
    return run_id


def print_summary(run_id: str) -> None:
    out = result_paths(run_id)
    with out["summary"].open(newline="") as f:
        rows = list(csv.DictReader(f))
    print(
        f"\n{'scenario':<14}{'n':>5} {'op':<13}{'ok':>6}{'err':>5}{'p50':>8}{'p95':>8}"
        f"{'p99':>8}{'ok/s':>8}{'confl':>7}{'thr':>5}{'cap/op':>8}"
    )
    for r in rows:
        print(
            f"{r['scenario']:<14}{r['students']:>5} {r['op']:<13}{r['ok']:>6}{r['errors']:>5}"
            f"{float(r['p50_ms']):>8.1f}{float(r['p95_ms']):>8.1f}{float(r['p99_ms']):>8.1f}"
            f"{float(r['ok_per_s']):>8.1f}{r['tx_conflicts']:>7}{r['throttles']:>5}"
            f"{float(r['capacity_per_op']):>8.2f}"
        )
    with out["checks"].open(newline="") as f:
        for r in csv.DictReader(f):
            print(
                f"{r['scenario']} {r['students']}: no lost updates = {r['no_lost_updates']}"
                f" (votes {r['votes_ok']}/{r['vote_markers']}/{r['vote_count_sum']},"
                f" comments {r['comments_ok']}/{r['comment_items']}/{r['comment_count_sum']})"
            )
    print(f"\nResults: {out['summary'].parent}/bench-{run_id}-*")


def int_list(text: str) -> list[int]:
    return [int(part) for part in text.split(",") if part]


def scenario_list(text: str) -> list[str]:
    chosen = [part for part in text.split(",") if part]
    unknown = set(chosen) - set(SCENARIOS)
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown scenario(s): {', '.join(sorted(unknown))}")
    return chosen


def main() -> int:
    global RESULTS
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=RESULTS, help="results directory")
    commands = parser.add_subparsers(dest="command", required=True)

    run_cmd = commands.add_parser("run", help="run the load scenarios on a new table")
    run_cmd.add_argument("--endpoint-url", default=db.endpoint_url(), help="unset = AWS")
    run_cmd.add_argument("--scenarios", type=scenario_list, default=SCENARIOS)
    run_cmd.add_argument("--students", type=int_list, default=DEFAULT_STUDENTS)
    run_cmd.add_argument("--rooms", type=int, default=10, help="rooms in many-rooms")
    run_cmd.add_argument("--posts", type=int, default=Load.posts, help="ideas per student")
    run_cmd.add_argument("--votes", type=int, default=Load.votes, help="votes per student")
    run_cmd.add_argument("--comments", type=int, default=Load.comments, help="per student")
    run_cmd.add_argument("--scan-rooms", type=int, default=100)
    run_cmd.add_argument("--scan-ideas", type=int, default=30, help="ideas per room for the scan")
    run_cmd.add_argument("--provisioned", action="store_true", help="provisioned capacity table")
    run_cmd.add_argument("--keep-table", action="store_true")
    run_cmd.add_argument("--seed", type=int, default=4411)

    args = parser.parse_args()
    RESULTS = args.results
    try:
        if args.command == "run":
            run_id = run(
                args.endpoint_url,
                args.scenarios,
                args.students,
                provisioned=args.provisioned,
                n_rooms=args.rooms,
                load=Load(args.posts, args.votes, args.comments),
                scan_rooms=args.scan_rooms,
                scan_ideas=args.scan_ideas,
                seed=args.seed,
                keep_table=args.keep_table,
            )
            print_summary(run_id)
    except (BotoCoreError, ClientError) as err:
        print(f"Benchmark failed: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
