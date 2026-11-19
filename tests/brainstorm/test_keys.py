"""Tests for key builders, codes, and timestamps."""

from datetime import UTC, datetime

from brainstorm import keys


def test_iso_is_fixed_width_and_sorts_lexically():
    early = datetime(2026, 10, 18, 14, 5, 31, 0, tzinfo=UTC)
    late = datetime(2026, 10, 18, 14, 5, 31, 120000, tzinfo=UTC)
    assert keys.iso(early) == "2026-10-18T14:05:31.000Z"
    assert keys.iso(late) == "2026-10-18T14:05:31.120Z"
    assert keys.iso(early) < keys.iso(late)


def test_new_code_uses_unambiguous_alphabet():
    for _ in range(200):
        code = keys.new_code()
        assert len(code) == keys.CODE_LENGTH
        assert set(code) <= set(keys.CODE_ALPHABET)
        assert not set(code) & set("IL01O")


def test_room_partition_sort_order():
    # load_board depends on COMMENT# < IDEA# < META < USER# < VOTE#.
    ts = "2026-10-18T14:05:31.120Z"
    ordered = [
        keys.comment_sk("i", ts, "c"),
        keys.idea_sk(ts, "i"),
        keys.META,
        keys.user_key("u"),
        keys.vote_sk("u", "i"),
    ]
    assert ordered == sorted(ordered)


def test_room_id_from_pk():
    assert keys.room_id_from_pk(keys.room_pk("01JAB3K9")) == "01JAB3K9"
    assert keys.room_id_from_pk(keys.code_pk("K7QM4X")) is None
    assert keys.room_id_from_pk(keys.connection_pk("abc=")) is None
    assert keys.room_id_from_pk("ROOM#") is None
