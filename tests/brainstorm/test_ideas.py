"""Tests for idea, vote, and comment operations against DynamoDB Local."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from brainstorm import ideas, rooms
from brainstorm.errors import (
    AlreadyVotedError,
    IdeaNotFoundError,
    InvalidInputError,
    NotVotedError,
    RoomClosedError,
    RoomNotFoundError,
)


@pytest.fixture
def room(table):
    """An open room owned by ``prof``."""
    return rooms.create_room(table, "prof", "Topic")


def test_post_idea_copies_room_ttl(table, room):
    idea = ideas.post_idea(table, room["room_id"], "stu-1", "Roah", "Use a GSI")
    assert idea["expires_at"] == room["expires_at"]
    assert idea["vote_count"] == 0


def test_post_idea_rejects_long_body(table, room):
    with pytest.raises(InvalidInputError):
        ideas.post_idea(table, room["room_id"], "stu-1", "Roah", "x" * 501)


def test_no_posts_to_closed_room(table, room):
    rooms.close_room(table, room["room_id"], "prof")
    with pytest.raises(RoomClosedError):
        ideas.post_idea(table, room["room_id"], "stu-1", "Roah", "Too late")


def test_load_board_returns_meta_and_ideas_newest_first(table, room):
    rid = room["room_id"]
    first = ideas.post_idea(table, rid, "stu-1", "Roah", "First")
    second = ideas.post_idea(table, rid, "stu-2", "Sachin", "Second")
    rooms.join_room(table, rid, "stu-1", "Roah")
    ideas.vote(table, rid, "stu-1", first["SK"])
    board = ideas.load_board(table, rid)
    assert board["room"]["room_id"] == rid
    assert [i["idea_id"] for i in board["ideas"]] == [second["idea_id"], first["idea_id"]]
    assert board["comments"] == {}


def test_load_board_with_comments_groups_oldest_first(table, room):
    rid = room["room_id"]
    idea = ideas.post_idea(table, rid, "stu-1", "Roah", "Idea")
    c1 = ideas.add_comment(table, rid, idea["SK"], "stu-2", "Sachin", "One")
    c2 = ideas.add_comment(table, rid, idea["SK"], "stu-3", "Annie", "Two")
    board = ideas.load_board(table, rid, include_comments=True)
    assert board["ideas"][0]["comment_count"] == 2
    expected = [c1["comment_id"], c2["comment_id"]]
    assert [c["comment_id"] for c in board["comments"][idea["idea_id"]]] == expected
    listed = ideas.list_comments(table, rid, idea["SK"])
    assert [c["comment_id"] for c in listed] == expected


def test_load_board_missing_room(table):
    with pytest.raises(RoomNotFoundError):
        ideas.load_board(table, "nope")


def test_list_ideas_pages(table, room):
    rid = room["room_id"]
    posted = [ideas.post_idea(table, rid, "stu", "S", f"Idea {n}")["idea_id"] for n in range(5)]
    page1, key = ideas.list_ideas(table, rid, limit=3)
    page2, _ = ideas.list_ideas(table, rid, limit=3, start_key=key)
    assert [i["idea_id"] for i in page1 + page2] == posted[::-1]


def test_vote_once_per_user_and_counts(table, room):
    rid = room["room_id"]
    idea = ideas.post_idea(table, rid, "stu-1", "Roah", "Idea")
    ideas.vote(table, rid, "stu-1", idea["SK"])
    ideas.vote(table, rid, "stu-2", idea["SK"])
    with pytest.raises(AlreadyVotedError):
        ideas.vote(table, rid, "stu-1", idea["SK"])
    assert ideas.load_board(table, rid)["ideas"][0]["vote_count"] == 2
    assert ideas.my_votes(table, rid, "stu-1") == {idea["idea_id"]}


def test_unvote_decrements_and_requires_vote(table, room):
    rid = room["room_id"]
    idea = ideas.post_idea(table, rid, "stu-1", "Roah", "Idea")
    with pytest.raises(NotVotedError):
        ideas.unvote(table, rid, "stu-1", idea["SK"])
    ideas.vote(table, rid, "stu-1", idea["SK"])
    ideas.unvote(table, rid, "stu-1", idea["SK"])
    assert ideas.load_board(table, rid)["ideas"][0]["vote_count"] == 0
    assert ideas.my_votes(table, rid, "stu-1") == set()


def test_vote_on_missing_idea_creates_nothing(table, room):
    rid = room["room_id"]
    fake_sk = "IDEA#2026-01-01T00:00:00.000Z#missing"
    with pytest.raises(IdeaNotFoundError):
        ideas.vote(table, rid, "stu-1", fake_sk)
    assert ideas.load_board(table, rid)["ideas"] == []
    assert ideas.my_votes(table, rid, "stu-1") == set()


def test_no_votes_in_closed_room(table, room):
    rid = room["room_id"]
    idea = ideas.post_idea(table, rid, "stu-1", "Roah", "Idea")
    rooms.close_room(table, rid, "prof")
    with pytest.raises(RoomClosedError):
        ideas.vote(table, rid, "stu-1", idea["SK"])


def test_comment_on_missing_idea(table, room):
    with pytest.raises(IdeaNotFoundError):
        ideas.add_comment(table, room["room_id"], "IDEA#2026-01-01T00:00:00.000Z#x", "s", "S", "Hi")


def test_top_ideas_sorts_by_votes(table, room):
    rid = room["room_id"]
    low = ideas.post_idea(table, rid, "a", "A", "Low")
    high = ideas.post_idea(table, rid, "b", "B", "High")
    for user in ("u1", "u2"):
        ideas.vote(table, rid, user, high["SK"])
    ideas.vote(table, rid, "u1", low["SK"])
    top = ideas.top_ideas(ideas.load_board(table, rid), n=2)
    assert [i["idea_id"] for i in top] == [high["idea_id"], low["idea_id"]]


def test_idea_id_from_sk_rejects_other_keys():
    with pytest.raises(InvalidInputError):
        ideas.idea_id_from_sk("VOTE#u#i")


def test_concurrent_votes_are_all_counted(table, room):
    rid = room["room_id"]
    idea = ideas.post_idea(table, rid, "stu-1", "Roah", "Popular")
    voters = [f"stu-{n}" for n in range(20)]
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(lambda user: ideas.vote(table, rid, user, idea["SK"]), voters))
    assert ideas.load_board(table, rid)["ideas"][0]["vote_count"] == len(voters)
