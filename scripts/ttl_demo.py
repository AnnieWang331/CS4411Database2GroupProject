"""Show TTL deleting expired rooms: make short-lived rooms now, check later what TTL removed.

Usage (global options such as --table and --results go before start/check):
  python scripts/ttl_demo.py start [--rooms N] [--minutes M] [--endpoint-url URL] [--table NAME]
  python scripts/ttl_demo.py check RUN_ID [--api-url URL] [--endpoint-url URL] [--table NAME]

``start`` creates N rooms that expire after M minutes, fills each with participants, ideas, votes
and a comment, and writes every item's key and ``expires_at`` to
``benchmarks/results/ttl-<RUN_ID>-items.csv`` (or the ``--results`` directory).

``check`` (run it as often as you like, at least every 12 hours: the stream only keeps records
for 24) looks at every item again and appends to ``ttl-<RUN_ID>-checks.csv`` whether it is still
there. It reads the table's stream for the REMOVE records of those items, saves them to
``ttl-<RUN_ID>-records.jsonl`` and their delete times and delays to ``ttl-<RUN_ID>-deletes.csv``.
It also checks that reads hide each room once it has expired, even while TTL hasn't deleted it
yet (``ttl-<RUN_ID>-reads.csv``); with ``--api-url`` it does that through the HTTP API as well.
"""

import argparse
import csv
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import urlopen

from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import BotoCoreError, ClientError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from brainstorm import db, ideas, keys, rooms  # noqa: E402 - needs the sys.path entry above
from brainstorm.errors import RoomNotFoundError  # noqa: E402
from brainstorm.stream_events import (  # noqa: E402
    TTL_PRINCIPAL,
    from_get_records,
    is_ttl_delete,
)

RESULTS = ROOT / "benchmarks" / "results"
INSTRUCTOR = "prof-ttl-demo"
STUDENTS = {"stu-ttl-a": "Ada", "stu-ttl-b": "Bao"}
# DynamoDB Streams can return empty pages from an open shard before its newest records.
EMPTY_PAGES_BEFORE_STOP = 3

ITEM_FIELDS = ["room_id", "code", "pk", "sk", "entity_type", "expires_at"]
CHECK_FIELDS = ["checked_at", "pk", "sk", "entity_type", "expires_at", "present", "past_expiry_s"]
DELETE_FIELDS = ["pk", "sk", "entity_type", "expires_at", "deleted_at", "delay_s", "ttl_delete"]
READ_FIELDS = [
    "checked_at",
    "room_id",
    "code",
    "past_expiry_s",
    "meta_present",
    "get_room",
    "resolve_code",
    "http_get_room",
    "http_get_code",
]

_deserializer = TypeDeserializer()


def paths(run_id: str) -> dict[str, Path]:
    """Result files of one run."""
    return {
        name: RESULTS / f"ttl-{run_id}-{name}.{ext}"
        for name, ext in [
            ("items", "csv"),
            ("checks", "csv"),
            ("deletes", "csv"),
            ("records", "jsonl"),
            ("reads", "csv"),
        ]
    }


def fill_room(table, minutes: int, n: int) -> list[dict[str, Any]]:
    """Create one short-lived room with some activity; return every item it has."""
    room = rooms.create_room(
        table, INSTRUCTOR, f"TTL demo room {n}", ttl=timedelta(minutes=minutes)
    )
    rid = room["room_id"]
    for user_id, name in STUDENTS.items():
        rooms.join_room(table, rid, user_id, name)
    posted = [
        ideas.post_idea(table, rid, uid, name, f"{name}'s idea in room {n}")
        for uid, name in STUDENTS.items()
    ]
    ideas.vote(table, rid, "stu-ttl-b", posted[0]["SK"])
    ideas.vote(table, rid, "stu-ttl-a", posted[1]["SK"])
    ideas.add_comment(table, rid, posted[0]["SK"], "stu-ttl-b", "Bao", "Agreed")
    items = rooms.query_all(
        table, KeyConditionExpression=Key("PK").eq(keys.room_pk(rid)), ConsistentRead=True
    )
    code_item = table.get_item(
        Key={"PK": keys.code_pk(room["code"]), "SK": keys.META}, ConsistentRead=True
    )["Item"]
    return [
        {
            "room_id": rid,
            "code": room["code"],
            "pk": item["PK"],
            "sk": item["SK"],
            "entity_type": item["entity_type"],
            "expires_at": int(item["expires_at"]),
        }
        for item in [*items, code_item]
    ]


def start(table, n_rooms: int, minutes: int) -> str:
    """Create the rooms and write the items file; return the run id."""
    run_id = keys.utc_now().strftime("%Y%m%dT%H%M%SZ")
    rows = [row for n in range(1, n_rooms + 1) for row in fill_room(table, minutes, n)]
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_csv(paths(run_id)["items"], ITEM_FIELDS, rows)
    expires = datetime.fromtimestamp(rows[0]["expires_at"], UTC)
    print(f"Run {run_id}: {n_rooms} rooms, {len(rows)} items, expiring at {expires:%H:%M:%S} UTC")
    for row in rows:
        if row["entity_type"] == "ROOM":
            print(f"  room {row['room_id']}  code {row['code']}")
    print(f"Check later with: python scripts/ttl_demo.py check {run_id}")
    return run_id


def read_stream(streams, stream_arn: str) -> list[dict[str, Any]]:
    """Return every record still in the stream (the last 24 hours), from all shards."""
    shards, start_after = [], None
    while True:
        kwargs = {"StreamArn": stream_arn}
        if start_after:
            kwargs["ExclusiveStartShardId"] = start_after
        desc = streams.describe_stream(**kwargs)["StreamDescription"]
        shards.extend(desc["Shards"])
        start_after = desc.get("LastEvaluatedShardId")
        if not start_after:
            break

    records = []
    for shard in shards:
        closed = "EndingSequenceNumber" in shard["SequenceNumberRange"]
        iterator = streams.get_shard_iterator(
            StreamArn=stream_arn, ShardId=shard["ShardId"], ShardIteratorType="TRIM_HORIZON"
        )["ShardIterator"]
        empty = 0
        while iterator:
            page = streams.get_records(ShardIterator=iterator, Limit=1000)
            records.extend(page["Records"])
            iterator = page.get("NextShardIterator")
            empty = 0 if page["Records"] else empty + 1
            # A closed shard ends when it stops handing out iterators; an open one never does.
            if not closed and empty >= EMPTY_PAGES_BEFORE_STOP:
                break
    return records


def record_key(record: dict[str, Any]) -> tuple[str, str]:
    """(PK, SK) of a stream record."""
    k = record["dynamodb"]["Keys"]
    return _deserializer.deserialize(k["PK"]), _deserializer.deserialize(k["SK"])


def http_status(url: str) -> int:
    """Status code of a GET (only the status matters here)."""
    try:
        with urlopen(url, timeout=10) as resp:
            return resp.status
    except HTTPError as err:
        return err.code


def read_check(table, row: dict[str, Any], now: int, api_url: str | None) -> dict[str, Any]:
    """How the app's reads see one room: hidden (not found) or visible."""

    def seen(read) -> str:
        try:
            read()
        except RoomNotFoundError:
            return "hidden"
        return "visible"

    meta = table.get_item(Key={"PK": row["pk"], "SK": keys.META}, ConsistentRead=True).get("Item")
    result = {
        "room_id": row["room_id"],
        "code": row["code"],
        "past_expiry_s": now - row["expires_at"],
        "meta_present": meta is not None,
        "get_room": seen(lambda: rooms.get_room(table, row["room_id"], consistent=True)),
        "resolve_code": seen(lambda: rooms.resolve_code(table, row["code"])),
        "http_get_room": "",
        "http_get_code": "",
    }
    if api_url:
        base = api_url.rstrip("/")
        result["http_get_room"] = http_status(f"{base}/rooms/{row['room_id']}")
        result["http_get_code"] = http_status(f"{base}/codes/{row['code']}")
    return result


def check(table, streams, run_id: str, api_url: str | None) -> None:
    """Look at the run's items now; record what TTL has deleted and when."""
    files = paths(run_id)
    items = read_csv(files["items"])
    for row in items:
        row["expires_at"] = int(row["expires_at"])
    now_dt = keys.utc_now()
    now, checked_at = keys.epoch(now_dt), keys.iso(now_dt)

    checks = []
    for row in items:
        found = table.get_item(Key={"PK": row["pk"], "SK": row["sk"]}, ConsistentRead=True)
        checks.append(
            {
                "checked_at": checked_at,
                **{f: row[f] for f in ["pk", "sk", "entity_type", "expires_at"]},
                "present": "Item" in found,
                "past_expiry_s": now - row["expires_at"],
            }
        )
    append_csv(files["checks"], CHECK_FIELDS, checks)

    reads = [
        {"checked_at": checked_at, **read_check(table, row, now, api_url)}
        for row in items
        if row["entity_type"] == "ROOM"
    ]
    append_csv(files["reads"], READ_FIELDS, reads)

    by_key = {(row["pk"], row["sk"]): row for row in items}
    # Saved in the shape Lambda delivers, so a record can be used as a test fixture as it is.
    removes = [
        from_get_records(r)
        for r in read_stream(streams, table.latest_stream_arn)
        if r["eventName"] == "REMOVE" and record_key(r) in by_key
    ]
    deletes = {(d["pk"], d["sk"]): d for d in read_csv(files["deletes"])}
    saved = set(read_lines(files["records"]))
    with files["records"].open("a") as out:
        for record in removes:
            line = json.dumps(record, sort_keys=True)
            if line not in saved:
                saved.add(line)
                out.write(line + "\n")
            row = by_key[record_key(record)]
            deleted = record["dynamodb"]["ApproximateCreationDateTime"]
            deletes[(row["pk"], row["sk"])] = {
                **{f: row[f] for f in ["pk", "sk", "entity_type", "expires_at"]},
                "deleted_at": keys.iso(datetime.fromtimestamp(deleted, UTC)),
                "delay_s": deleted - row["expires_at"],
                "ttl_delete": is_ttl_delete(record),
            }
    write_csv(files["deletes"], DELETE_FIELDS, sorted(deletes.values(), key=lambda d: d["delay_s"]))

    gone = sum(1 for c in checks if not c["present"])
    print(f"Run {run_id} at {checked_at}: {gone}/{len(checks)} items gone")
    print(
        f"  {len(deletes)} REMOVE records found in the stream so far (saved to {files['deletes']})"
    )
    if deletes:
        delays = sorted(int(d["delay_s"]) for d in deletes.values())
        ttl = sum(str(d["ttl_delete"]) == "True" for d in deletes.values())
        print(f"  delete delay after expires_at: min {delays[0]}s, max {delays[-1]}s")
        print(f"  {ttl}/{len(deletes)} made by TTL (userIdentity {TTL_PRINCIPAL})")
    for r in reads:
        http = f", HTTP room {r['http_get_room']} code {r['http_get_code']}" if api_url else ""
        print(
            f"  room {r['room_id'][:8]}: item {'present' if r['meta_present'] else 'gone'}, "
            f"get_room {r['get_room']}, resolve_code {r['resolve_code']}{http}"
        )


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def read_lines(path: Path) -> list[str]:
    return path.read_text().splitlines() if path.exists() else []


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def append_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    new = not path.exists()
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if new:
            writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    global RESULTS
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint-url", default=db.endpoint_url(), help="e.g. localhost:8000")
    parser.add_argument("--table", default=db.table_name(), help="table name")
    parser.add_argument("--results", type=Path, default=RESULTS, help="where result files go")
    sub = parser.add_subparsers(dest="command", required=True)
    start_p = sub.add_parser("start", help="create short-lived rooms")
    start_p.add_argument("--rooms", type=int, default=3, help="number of rooms")
    start_p.add_argument("--minutes", type=int, default=5, help="room lifetime (TTL) in minutes")
    check_p = sub.add_parser("check", help="see what TTL has deleted so far")
    check_p.add_argument("run_id", help="the run id printed by start")
    check_p.add_argument("--api-url", help="also check reads through this HTTP API base URL")
    args = parser.parse_args()
    RESULTS = args.results

    table = db.table(args.table, args.endpoint_url)
    try:
        if args.command == "start":
            start(table, args.rooms, args.minutes)
        else:
            if not paths(args.run_id)["items"].exists():
                print(f"No run {args.run_id} in {RESULTS}", file=sys.stderr)
                return 1
            check(table, db.streams_client(args.endpoint_url), args.run_id, args.api_url)
    except (BotoCoreError, ClientError) as err:
        print(f"TTL demo failed: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
