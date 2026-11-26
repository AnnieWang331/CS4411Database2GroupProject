-- The access patterns from docs/data-model.md section 1, against sql/schema.sql. Each one is a
-- function named after its Python counterpart in rooms.py/ideas.py, so the two can be compared
-- side by side. Rejections raise an exception whose message is the API's error code
-- (room_closed, already_voted, ...). Patterns 19-21 (WebSocket connections) are left out: they're
-- plumbing for live updates, which a relational database doesn't provide by itself.
--
-- Concurrency: in DynamoDB there are no locks, so every write repeats the "room is open" rule
-- as a condition inside its transaction (data-model 4). Here a write reads the room with
-- FOR SHARE first. That row lock lasts until the transaction ends, so a close (which needs
-- FOR UPDATE) waits for writes already in progress, and writes that start after it see the room
-- closed. Shared locks don't block each other, so a whole class posting and voting at once
-- doesn't conflict on the room row, which is what limited the DynamoDB benchmark.

SET search_path = brainstorm;

-- Raise an error whose message is an API error code.
CREATE FUNCTION reject(code text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '%', code;
END $$;

-- The "room is open" check every write in a room makes, holding a shared lock on the room
-- until the transaction ends. Missing or expired rooms are room_not_found, closed ones
-- room_closed (expired rooms can still be in the table until pattern 18 runs).
CREATE FUNCTION lock_open_room(p_room_id uuid) RETURNS rooms
LANGUAGE plpgsql AS $$
DECLARE
    r rooms;
BEGIN
    SELECT * INTO r FROM rooms WHERE room_id = p_room_id FOR SHARE;
    IF NOT FOUND OR r.expires_at <= now() THEN
        PERFORM reject('room_not_found');
    ELSIF r.status <> 'open' THEN
        PERFORM reject('room_closed');
    END IF;
    RETURN r;
END $$;

-- Turn a foreign key or unique violation into the API's error code.
CREATE FUNCTION reject_constraint(constraint_name text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM reject(CASE constraint_name
        WHEN 'ideas_author_joined'    THEN 'not_participant'
        WHEN 'votes_voter_joined'     THEN 'not_participant'
        WHEN 'comments_author_joined' THEN 'not_participant'
        WHEN 'votes_idea_in_room'     THEN 'idea_not_found'
        WHEN 'comments_idea_in_room'  THEN 'idea_not_found'
        WHEN 'votes_pkey'             THEN 'already_voted'
        ELSE 'invalid_input'
    END);
END $$;

-- 1. Create a room with a unique join code. The partial unique index rooms_open_code does what
-- DynamoDB needs a second item and a transaction for. Retries a taken code up to 5 times, like
-- rooms.create_room.
CREATE FUNCTION create_room(p_owner_id text, p_topic text, p_ttl interval DEFAULT '24 hours')
RETURNS rooms
LANGUAGE plpgsql AS $$
DECLARE
    alphabet constant text := 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
    new_code text;
    r rooms;
BEGIN
    FOR attempt IN 1..5 LOOP
        SELECT string_agg(substr(alphabet, 1 + floor(random() * 31)::int, 1), '')
          INTO new_code FROM generate_series(1, 6);
        BEGIN
            INSERT INTO rooms (code, topic, owner_id, expires_at)
            VALUES (new_code, btrim(p_topic), p_owner_id, now() + p_ttl)
            RETURNING * INTO r;
            RETURN r;
        EXCEPTION WHEN unique_violation THEN
            -- the code belongs to another open room; try another one
        END;
    END LOOP;
    PERFORM reject('code_unavailable');
END $$;

-- 2. Look up an open room from its join code.
CREATE FUNCTION resolve_code(p_code text) RETURNS rooms
LANGUAGE plpgsql AS $$
DECLARE
    r rooms;
BEGIN
    SELECT * INTO r FROM rooms
     WHERE code = upper(p_code) AND status = 'open' AND expires_at > now();
    IF NOT FOUND THEN
        PERFORM reject('room_not_found');
    END IF;
    RETURN r;
END $$;

-- 3. Get a room's info (closed rooms too, but not expired ones).
CREATE FUNCTION get_room(p_room_id uuid) RETURNS rooms
LANGUAGE plpgsql AS $$
DECLARE
    r rooms;
BEGIN
    SELECT * INTO r FROM rooms WHERE room_id = p_room_id AND expires_at > now();
    IF NOT FOUND THEN
        PERFORM reject('room_not_found');
    END IF;
    RETURN r;
END $$;

-- 4. Join a room. Joining again only changes the display name; joined_at stays the first one.
CREATE FUNCTION join_room(p_room_id uuid, p_user_id text, p_display_name text)
RETURNS participants
LANGUAGE plpgsql AS $$
DECLARE
    p participants;
BEGIN
    PERFORM lock_open_room(p_room_id);
    INSERT INTO participants (room_id, user_id, display_name)
    VALUES (p_room_id, p_user_id, btrim(p_display_name))
    ON CONFLICT (room_id, user_id) DO UPDATE SET display_name = excluded.display_name
    RETURNING * INTO p;
    RETURN p;
END $$;

-- 5. List the people in a room.
CREATE FUNCTION list_participants(p_room_id uuid) RETURNS SETOF participants
LANGUAGE sql STABLE AS $$
    SELECT * FROM participants WHERE room_id = p_room_id ORDER BY joined_at;
$$;

-- 6. Post an idea (open rooms only, and only after joining).
CREATE FUNCTION post_idea(p_room_id uuid, p_author_id text, p_body text) RETURNS ideas
LANGUAGE plpgsql AS $$
DECLARE
    i ideas;
    c text;
BEGIN
    PERFORM lock_open_room(p_room_id);
    INSERT INTO ideas (room_id, author_id, body)
    VALUES (p_room_id, p_author_id, btrim(p_body))
    RETURNING * INTO i;
    RETURN i;
EXCEPTION WHEN foreign_key_violation THEN
    GET STACKED DIAGNOSTICS c = CONSTRAINT_NAME;
    PERFORM reject_constraint(c);
END $$;

-- 7. Load the board, newest ideas first. The counts and the author's current name come from
-- joins; DynamoDB stores both on the idea so the board is one Query.
CREATE VIEW board_ideas AS
SELECT i.room_id, i.idea_id, i.author_id, p.display_name AS author_name, i.body, i.created_at,
       (SELECT count(*) FROM votes v WHERE v.idea_id = i.idea_id)    AS vote_count,
       (SELECT count(*) FROM comments c WHERE c.idea_id = i.idea_id) AS comment_count
  FROM ideas i
  JOIN participants p ON p.room_id = i.room_id AND p.user_id = i.author_id;

CREATE FUNCTION load_board(p_room_id uuid) RETURNS SETOF board_ideas
LANGUAGE sql STABLE AS $$
    SELECT b.* FROM board_ideas b
      JOIN rooms r ON r.room_id = b.room_id AND r.expires_at > now()
     WHERE b.room_id = p_room_id
     ORDER BY b.created_at DESC, b.idea_id DESC;
$$;

-- 8. Load the board with comments: the ideas from pattern 7 plus every comment in the room.
-- (DynamoDB gets both from one Query, because comments sort before META in the same partition.)
CREATE FUNCTION room_comments(p_room_id uuid)
RETURNS TABLE (idea_id uuid, comment_id uuid, author_name text, body text, created_at timestamptz)
LANGUAGE sql STABLE AS $$
    SELECT c.idea_id, c.comment_id, p.display_name, c.body, c.created_at
      FROM comments c
      JOIN participants p ON p.room_id = c.room_id AND p.user_id = c.author_id
      JOIN rooms r ON r.room_id = c.room_id AND r.expires_at > now()
     WHERE c.room_id = p_room_id
     ORDER BY c.idea_id, c.created_at;
$$;

-- 9. Page through ideas, newest first. Pass the last row's created_at and idea_id to get the
-- next page (keyset pagination, like DynamoDB's LastEvaluatedKey).
CREATE FUNCTION list_ideas(p_room_id uuid, p_limit int DEFAULT 20,
                           p_after_created_at timestamptz DEFAULT NULL,
                           p_after_idea_id uuid DEFAULT NULL)
RETURNS SETOF board_ideas
LANGUAGE sql STABLE AS $$
    SELECT * FROM load_board(p_room_id) b
     WHERE p_after_created_at IS NULL
        OR (b.created_at, b.idea_id) < (p_after_created_at, p_after_idea_id)
     LIMIT least(greatest(p_limit, 1), 100);
$$;

-- 10. Top-voted ideas. The database sorts by the count; in DynamoDB the app sorts the board.
CREATE FUNCTION top_ideas(p_room_id uuid, p_n int DEFAULT 10) RETURNS SETOF board_ideas
LANGUAGE sql STABLE AS $$
    SELECT * FROM load_board(p_room_id) ORDER BY vote_count DESC, created_at LIMIT p_n;
$$;

-- 11. Vote for an idea, once per person: the votes primary key rejects a second vote. Two
-- students voting for the same idea insert different rows, so they don't wait on each other.
CREATE FUNCTION vote(p_room_id uuid, p_user_id text, p_idea_id uuid) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    c text;
BEGIN
    PERFORM lock_open_room(p_room_id);
    INSERT INTO votes (room_id, idea_id, user_id) VALUES (p_room_id, p_idea_id, p_user_id);
EXCEPTION WHEN foreign_key_violation OR unique_violation THEN
    GET STACKED DIAGNOSTICS c = CONSTRAINT_NAME;
    PERFORM reject_constraint(c);
END $$;

-- 12. Take a vote back.
CREATE FUNCTION unvote(p_room_id uuid, p_user_id text, p_idea_id uuid) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM lock_open_room(p_room_id);
    DELETE FROM votes WHERE room_id = p_room_id AND idea_id = p_idea_id AND user_id = p_user_id;
    IF NOT FOUND THEN
        IF EXISTS (SELECT 1 FROM ideas WHERE room_id = p_room_id AND idea_id = p_idea_id) THEN
            PERFORM reject('not_voted');
        END IF;
        PERFORM reject('idea_not_found');
    END IF;
END $$;

-- 13. Which ideas I voted for in a room.
CREATE FUNCTION my_votes(p_room_id uuid, p_user_id text) RETURNS SETOF uuid
LANGUAGE sql STABLE AS $$
    SELECT idea_id FROM votes WHERE room_id = p_room_id AND user_id = p_user_id;
$$;

-- 14. Comment on an idea.
CREATE FUNCTION add_comment(p_room_id uuid, p_author_id text, p_idea_id uuid, p_body text)
RETURNS comments
LANGUAGE plpgsql AS $$
DECLARE
    cm comments;
    c text;
BEGIN
    PERFORM lock_open_room(p_room_id);
    INSERT INTO comments (room_id, idea_id, author_id, body)
    VALUES (p_room_id, p_idea_id, p_author_id, btrim(p_body))
    RETURNING * INTO cm;
    RETURN cm;
EXCEPTION WHEN foreign_key_violation THEN
    GET STACKED DIAGNOSTICS c = CONSTRAINT_NAME;
    PERFORM reject_constraint(c);
END $$;

-- 15. The comments on one idea, oldest first.
CREATE FUNCTION list_comments(p_room_id uuid, p_idea_id uuid)
RETURNS TABLE (comment_id uuid, author_name text, body text, created_at timestamptz)
LANGUAGE sql STABLE AS $$
    SELECT comment_id, author_name, body, created_at
      FROM room_comments(p_room_id) WHERE idea_id = p_idea_id;
$$;

-- 16. Close a room (owner only). Its code is free again straight away, because the unique
-- index only covers open rooms. FOR UPDATE waits for writes holding the room FOR SHARE.
CREATE FUNCTION close_room(p_room_id uuid, p_owner_id text) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    r rooms;
BEGIN
    SELECT * INTO r FROM rooms WHERE room_id = p_room_id FOR UPDATE;
    IF NOT FOUND OR r.expires_at <= now() THEN
        PERFORM reject('room_not_found');
    ELSIF r.owner_id <> p_owner_id THEN
        PERFORM reject('not_room_owner');
    ELSIF r.status <> 'open' THEN
        PERFORM reject('room_closed');
    END IF;
    UPDATE rooms SET status = 'closed', closed_at = now() WHERE room_id = p_room_id;
END $$;

-- 17. An instructor's rooms, newest first (index rooms_owner; DynamoDB uses GSI1).
CREATE FUNCTION list_owner_rooms(p_owner_id text) RETURNS SETOF rooms
LANGUAGE sql STABLE AS $$
    SELECT * FROM rooms
     WHERE owner_id = p_owner_id AND expires_at > now()
     ORDER BY created_at DESC;
$$;

-- 18. Delete old rooms. DynamoDB's TTL does this for free; here something has to run it on a
-- schedule (cron, or the pg_cron extension). Deleting a room cascades to everything in it.
-- Returns how many rooms it deleted.
CREATE FUNCTION delete_expired_rooms() RETURNS bigint
LANGUAGE sql AS $$
    WITH gone AS (DELETE FROM rooms WHERE expires_at <= now() RETURNING 1)
    SELECT count(*) FROM gone;
$$;
