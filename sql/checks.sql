-- Checks that the schema and functions enforce the same rules as the DynamoDB version
-- (data-model 4): each step tries something the app must reject and fails the script if it
-- isn't rejected with the right error. Run after schema.sql and queries.sql; it prints
-- "all checks passed" at the end.

SET search_path = brainstorm;
SET client_min_messages = notice;

-- Run a statement and fail unless it raises an error whose message (for our own rejections) or
-- SQLSTATE name (for constraint violations) is `expected`.
CREATE FUNCTION pg_temp.expect_error(label text, stmt text, expected text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE stmt;
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM = expected
           OR (expected = 'unique_violation' AND SQLSTATE = '23505')
           OR (expected = 'check_violation' AND SQLSTATE = '23514') THEN
            RAISE NOTICE 'ok: % (%)', label, expected;
            RETURN;
        END IF;
        RAISE EXCEPTION 'check failed: % raised "%" (%), expected %', label, SQLERRM, SQLSTATE,
            expected;
    END;
    RAISE EXCEPTION 'check failed: % was accepted, expected %', label, expected;
END $$;

DO $$
DECLARE
    room rooms;
    other rooms;
    old_room rooms;
    idea ideas;
    n bigint;
BEGIN
    room := create_room('prof-lee', 'Indexing strategies');
    PERFORM join_room(room.room_id, 'stu-1', 'Roah');
    PERFORM join_room(room.room_id, 'stu-2', 'Sachin');
    idea := post_idea(room.room_id, 'stu-1', 'Use a GSI for top-voted ideas');

    -- Join codes
    ASSERT resolve_code(lower(room.code)) = room, 'a code resolves to its room, any case';
    PERFORM pg_temp.expect_error('two open rooms with one code',
        format('INSERT INTO rooms (code, topic, owner_id, expires_at)
                VALUES (%L, %L, %L, now() + interval %L)', room.code, 't', 'x', '1 hour'),
        'unique_violation');
    PERFORM pg_temp.expect_error('a code outside the alphabet',
        $q$INSERT INTO rooms (code, topic, owner_id, expires_at)
           VALUES ('ABCDE0', 't', 'x', now() + interval '1 hour')$q$,
        'check_violation');

    -- Input limits
    PERFORM pg_temp.expect_error('a 501-character idea',
        format('SELECT post_idea(%L, %L, %L)', room.room_id, 'stu-1', repeat('x', 501)),
        'check_violation');
    PERFORM pg_temp.expect_error('a blank comment',
        format('SELECT add_comment(%L, %L, %L, %L)', room.room_id, 'stu-2', idea.idea_id, '   '),
        'check_violation');

    -- Joining again keeps joined_at and changes the name, and old posts show the new name
    PERFORM join_room(room.room_id, 'stu-1', 'Roah K.');
    ASSERT (SELECT count(*) FROM participants WHERE room_id = room.room_id) = 2, 'rejoin';
    ASSERT (SELECT author_name FROM load_board(room.room_id)) = 'Roah K.', 'renamed author';

    -- Only people who joined can post, vote or comment
    PERFORM pg_temp.expect_error('posting without joining',
        format('SELECT post_idea(%L, %L, %L)', room.room_id, 'stranger', 'hi'), 'not_participant');
    PERFORM pg_temp.expect_error('voting without joining',
        format('SELECT vote(%L, %L, %L)', room.room_id, 'stranger', idea.idea_id),
        'not_participant');

    -- One vote per person, counted on the board
    PERFORM vote(room.room_id, 'stu-1', idea.idea_id);
    PERFORM vote(room.room_id, 'stu-2', idea.idea_id);
    PERFORM pg_temp.expect_error('voting twice',
        format('SELECT vote(%L, %L, %L)', room.room_id, 'stu-2', idea.idea_id), 'already_voted');
    ASSERT (SELECT vote_count FROM load_board(room.room_id)) = 2, 'vote count';
    ASSERT idea.idea_id IN (SELECT my_votes(room.room_id, 'stu-2')), 'my votes';
    PERFORM unvote(room.room_id, 'stu-2', idea.idea_id);
    PERFORM pg_temp.expect_error('taking back a vote you never cast',
        format('SELECT unvote(%L, %L, %L)', room.room_id, 'stu-2', idea.idea_id), 'not_voted');
    ASSERT (SELECT vote_count FROM load_board(room.room_id)) = 1, 'vote count after unvote';

    -- Ideas belong to their room
    other := create_room('prof-lee', 'Another class');
    PERFORM join_room(other.room_id, 'stu-1', 'Roah');
    PERFORM pg_temp.expect_error('voting for an idea from another room',
        format('SELECT vote(%L, %L, %L)', other.room_id, 'stu-1', idea.idea_id),
        'idea_not_found');
    PERFORM pg_temp.expect_error('voting for an idea that does not exist',
        format('SELECT vote(%L, %L, %L)', room.room_id, 'stu-1', uuidv7()), 'idea_not_found');

    -- Comments update the board's comment count
    PERFORM add_comment(room.room_id, 'stu-2', idea.idea_id, 'Client-side sort is enough');
    ASSERT (SELECT comment_count FROM load_board(room.room_id)) = 1, 'comment count';
    ASSERT (SELECT count(*) FROM list_comments(room.room_id, idea.idea_id)) = 1, 'comments';

    -- Only the owner closes a room, and a closed room takes nothing new
    PERFORM pg_temp.expect_error('closing someone else''s room',
        format('SELECT close_room(%L, %L)', room.room_id, 'stu-1'), 'not_room_owner');
    PERFORM close_room(room.room_id, 'prof-lee');
    PERFORM pg_temp.expect_error('closing a room twice',
        format('SELECT close_room(%L, %L)', room.room_id, 'prof-lee'), 'room_closed');
    PERFORM pg_temp.expect_error('posting in a closed room',
        format('SELECT post_idea(%L, %L, %L)', room.room_id, 'stu-1', 'late'), 'room_closed');
    PERFORM pg_temp.expect_error('voting in a closed room',
        format('SELECT vote(%L, %L, %L)', room.room_id, 'stu-2', idea.idea_id), 'room_closed');
    PERFORM pg_temp.expect_error('commenting in a closed room',
        format('SELECT add_comment(%L, %L, %L, %L)', room.room_id, 'stu-2', idea.idea_id, 'late'),
        'room_closed');
    PERFORM pg_temp.expect_error('joining a closed room',
        format('SELECT join_room(%L, %L, %L)', room.room_id, 'stu-3', 'Late'), 'room_closed');
    PERFORM pg_temp.expect_error('joining by a closed room''s code',
        format('SELECT resolve_code(%L)', room.code), 'room_not_found');
    ASSERT (SELECT count(*) FROM load_board(room.room_id)) = 1, 'a closed board stays readable';

    -- Closing frees the code for a new room
    INSERT INTO rooms (code, topic, owner_id, expires_at)
    VALUES (room.code, 'Reused code', 'prof-kim', now() + interval '1 hour');

    -- Expired rooms are hidden before the cleanup runs, then deleted with everything in them
    old_room := create_room('prof-lee', 'Last week', interval '-1 second');
    PERFORM pg_temp.expect_error('getting an expired room',
        format('SELECT get_room(%L)', old_room.room_id), 'room_not_found');
    PERFORM pg_temp.expect_error('joining an expired room',
        format('SELECT join_room(%L, %L, %L)', old_room.room_id, 'stu-1', 'Roah'),
        'room_not_found');
    ASSERT old_room.room_id NOT IN (SELECT room_id FROM list_owner_rooms('prof-lee')),
        'my rooms hides expired rooms';
    ASSERT (SELECT count(*) FROM list_owner_rooms('prof-lee')) = 2, 'my rooms';
    UPDATE rooms SET expires_at = now() - interval '1 second' WHERE room_id = room.room_id;
    n := delete_expired_rooms();
    ASSERT n = 2, format('cleanup deleted %s rooms, expected 2', n);
    ASSERT NOT EXISTS (SELECT 1 FROM ideas WHERE room_id = room.room_id), 'ideas cascade';
    ASSERT NOT EXISTS (SELECT 1 FROM votes WHERE room_id = room.room_id), 'votes cascade';
    ASSERT NOT EXISTS (SELECT 1 FROM comments WHERE room_id = room.room_id), 'comments cascade';

    -- Start the demo from an empty board
    DELETE FROM rooms;
    RAISE NOTICE 'all checks passed';
END $$;
