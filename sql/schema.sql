-- The brainstorm board as a relational schema (PostgreSQL 18), for comparing with the DynamoDB
-- single-table design in docs/data-model.md. docs/relational.md explains the differences.
--
-- Running it again starts over: everything is in the `brainstorm` schema, which is dropped first.

SET client_min_messages = warning;  -- hide the DROP ... CASCADE notices
DROP SCHEMA IF EXISTS brainstorm CASCADE;
CREATE SCHEMA brainstorm;
SET search_path = brainstorm;

-- Same alphabet as keys.CODE_ALPHABET: no I, L, O, 0 or 1.
CREATE DOMAIN join_code AS text CHECK (VALUE ~ '^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{6}$');

-- User ids are client-made strings, as in the DynamoDB version (X-User-Id).
CREATE DOMAIN user_id AS text CHECK (length(VALUE) BETWEEN 1 AND 128);

CREATE TABLE rooms (
    room_id    uuid        PRIMARY KEY DEFAULT uuidv7(),
    code       join_code   NOT NULL,
    topic      text        NOT NULL CHECK (length(btrim(topic)) BETWEEN 1 AND 200),
    status     text        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    owner_id   user_id     NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    closed_at  timestamptz,
    -- Only the room has an expiry. Deleting it removes everything in it (ON DELETE CASCADE),
    -- so nothing else needs a copy, unlike the DynamoDB items.
    expires_at timestamptz NOT NULL,
    CHECK ((status = 'closed') = (closed_at IS NOT NULL))
);

-- A code is unique among open rooms only, so closing a room frees its code without a separate
-- code item (DynamoDB's CODE#<code>). An open room past expires_at keeps its code until the
-- cleanup (pattern 18) deletes it: an index predicate can't use now().
CREATE UNIQUE INDEX rooms_open_code ON rooms (code) WHERE status = 'open';

-- Pattern 17, "my rooms", newest first. DynamoDB needs GSI1 for this.
CREATE INDEX rooms_owner ON rooms (owner_id, created_at DESC);

CREATE TABLE participants (
    room_id      uuid        NOT NULL REFERENCES rooms ON DELETE CASCADE,
    user_id      user_id     NOT NULL,
    display_name text        NOT NULL CHECK (length(btrim(display_name)) BETWEEN 1 AND 50),
    joined_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (room_id, user_id)
);

-- Authors and voters must have joined the room (a foreign key to participants). The DynamoDB
-- version doesn't check this (data-model 4.3), the web client always joins first.
-- Names aren't copied onto ideas and comments: a board load joins participants, so a new name
-- shows on old posts too.
CREATE TABLE ideas (
    idea_id    uuid        PRIMARY KEY DEFAULT uuidv7(),
    room_id    uuid        NOT NULL,
    author_id  user_id     NOT NULL,
    body       text        NOT NULL CHECK (length(btrim(body)) BETWEEN 1 AND 500),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ideas_author_joined
        FOREIGN KEY (room_id, author_id) REFERENCES participants ON DELETE CASCADE,
    UNIQUE (room_id, idea_id)  -- so votes and comments can reference an idea in their room
);

-- Pattern 7, newest ideas first.
CREATE INDEX ideas_room ON ideas (room_id, created_at DESC);

-- One vote per person per idea is the primary key. room_id is in it so that a vote for an idea
-- in another room fails on votes_idea_in_room instead of looking like a duplicate. There's no
-- vote_count column: a board load counts the rows, so there's no counter to keep in sync or to
-- contend on.
CREATE TABLE votes (
    room_id    uuid        NOT NULL,
    idea_id    uuid        NOT NULL,
    user_id    user_id     NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (room_id, idea_id, user_id),
    CONSTRAINT votes_idea_in_room
        FOREIGN KEY (room_id, idea_id) REFERENCES ideas (room_id, idea_id) ON DELETE CASCADE,
    CONSTRAINT votes_voter_joined
        FOREIGN KEY (room_id, user_id) REFERENCES participants ON DELETE CASCADE
);

-- Pattern 13, "which ideas did I vote for in this room".
CREATE INDEX votes_user ON votes (room_id, user_id);

CREATE TABLE comments (
    comment_id uuid        PRIMARY KEY DEFAULT uuidv7(),
    room_id    uuid        NOT NULL,
    idea_id    uuid        NOT NULL,
    author_id  user_id     NOT NULL,
    body       text        NOT NULL CHECK (length(btrim(body)) BETWEEN 1 AND 300),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT comments_idea_in_room
        FOREIGN KEY (room_id, idea_id) REFERENCES ideas (room_id, idea_id) ON DELETE CASCADE,
    CONSTRAINT comments_author_joined
        FOREIGN KEY (room_id, author_id) REFERENCES participants ON DELETE CASCADE
);

-- Pattern 15, an idea's comments oldest first.
CREATE INDEX comments_idea ON comments (idea_id, created_at);

-- Pattern 18 deletes by expiry.
CREATE INDEX rooms_expires ON rooms (expires_at);
