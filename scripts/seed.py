"""Seed a demo room with participants, ideas, votes, and comments, then print the board.

Usage: python scripts/seed.py [--endpoint-url URL] [--table NAME] [--hours N]

Run scripts/create_table.py first. Each run creates a new room and prints its join code.
"""

import argparse
import sys
from datetime import timedelta
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from brainstorm import db, ideas, rooms  # noqa: E402 - needs the sys.path entry above

INSTRUCTOR = "prof-demo"
TOPIC = "How should we index a classroom brainstorm board?"
STUDENTS = {"stu-annie": "Annie", "stu-roah": "Roah", "stu-sachin": "Sachin", "stu-haadi": "Haadi"}
IDEAS = [
    ("stu-annie", "Keep every room in one partition so one Query loads the board"),
    ("stu-roah", "Store vote counts on the idea with an atomic counter"),
    ("stu-sachin", "Use TTL so rooms clean themselves up after class"),
    ("stu-haadi", "Push new ideas to clients with DynamoDB Streams"),
]
# (voter, index into IDEAS)
VOTES = [
    ("stu-roah", 0),
    ("stu-sachin", 0),
    ("stu-haadi", 0),
    ("stu-annie", 1),
    ("stu-haadi", 1),
    ("stu-annie", 2),
]
COMMENTS = [
    ("stu-sachin", 0, "And it avoids joins entirely"),
    ("stu-annie", 3, "Streams plus a WebSocket API Gateway"),
]


def seed(table, hours: int) -> dict:
    """Create and populate one demo room; return its loaded board."""
    room = rooms.create_room(table, INSTRUCTOR, TOPIC, ttl=timedelta(hours=hours))
    rid = room["room_id"]
    for user_id, name in STUDENTS.items():
        rooms.join_room(table, rid, user_id, name)
    posted = [ideas.post_idea(table, rid, uid, STUDENTS[uid], body) for uid, body in IDEAS]
    for voter, index in VOTES:
        ideas.vote(table, rid, voter, posted[index]["SK"])
    for author, index, body in COMMENTS:
        ideas.add_comment(table, rid, posted[index]["SK"], author, STUDENTS[author], body)
    return ideas.load_board(table, rid, include_comments=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint-url", default=db.endpoint_url(), help="e.g. localhost:8000")
    parser.add_argument("--table", default=db.table_name(), help="table name")
    parser.add_argument("--hours", type=int, default=24, help="room lifetime (TTL) in hours")
    args = parser.parse_args()

    try:
        board = seed(db.table(args.table, args.endpoint_url), args.hours)
    except (BotoCoreError, ClientError) as err:
        print(f"Seeding failed: {err}", file=sys.stderr)
        return 1

    room = board["room"]
    print(f"Room {room['room_id']}  code {room['code']}  topic: {room['topic']}")
    for idea in ideas.top_ideas(board, n=len(board["ideas"])):
        votes = idea["vote_count"]
        print(f"  [{votes} vote{'' if votes == 1 else 's'}] {idea['author_name']}: {idea['body']}")
        for comment in board["comments"].get(idea["idea_id"], []):
            print(f"      - {comment['author_name']}: {comment['body']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
