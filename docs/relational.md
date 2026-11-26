# Relational baseline: the same board in PostgreSQL

This is issue #12: the brainstorm board's data model rebuilt as an ordinary relational schema,
so the report can compare the two designs pattern by pattern. `docs/data-model.md` section 7
has the short version; this has the runnable SQL and the full table.

The files are in `sql/`:

- `schema.sql`: six tables (rooms, participants, ideas, votes, comments; join codes are a
  column with a partial unique index) and their constraints.
- `queries.sql`: one function per access pattern in data-model section 1, named like its
  Python counterpart in `rooms.py`/`ideas.py` (`create_room`, `vote`, `load_board`, ...).
  Rejections raise the API's error code (`room_closed`, `already_voted`, ...).
- `checks.sql`: tries every action the app must reject and fails if one gets through.
- `demo.sql`: the same demo room as `scripts/seed.py`, then the board.

It's PostgreSQL 18 (for `uuidv7()`, which sorts by time like our DynamoDB ids). CI runs all four
files on every PR. To run it yourself, see "Run the relational baseline" in the README.

## Access patterns

The numbers are the patterns in data-model section 1. Patterns 19-21 (WebSocket connections)
aren't here: they exist for live updates, which is a separate comparison (below).

| # | Pattern | DynamoDB | PostgreSQL |
|---|---|---|---|
| 1 | Create a room with a unique code | Transaction: room item + `CODE#` item with `attribute_not_exists` | One `INSERT`; the partial unique index `rooms_open_code` rejects a taken code |
| 2 | Room from a join code | Strongly consistent `GetItem` on `CODE#<code>` | `SELECT ... WHERE code = ? AND status = 'open'` |
| 3 | Room info | `GetItem` on `META`, then check `expires_at` | `SELECT` by primary key, check `expires_at` |
| 4 | Join | Transaction: room condition check + `SET ... if_not_exists(joined_at)` | Lock the room `FOR SHARE`, `INSERT ... ON CONFLICT DO UPDATE` |
| 5 | People in a room | `Query` on `USER#` | `SELECT` on the primary key `(room_id, user_id)` |
| 6 | Post an idea | Transaction: room check + `Put` | Lock the room `FOR SHARE`, `INSERT`; a foreign key requires the author to have joined |
| 7 | Load the board | One `Query`, counts and names stored on each idea | Join ideas to participants (for the name) and count votes and comments |
| 8 | Board with comments | Same `Query`, wider range (comments sort before `META`) | A second query for the room's comments |
| 9 | Page through ideas | `Limit` + `LastEvaluatedKey` | Keyset pagination on `(created_at, idea_id)` |
| 10 | Top-voted ideas | The app sorts the board | `ORDER BY vote_count DESC` |
| 11 | Vote once | Transaction: room check + vote marker with `attribute_not_exists` + `ADD vote_count 1` | Lock the room `FOR SHARE`, `INSERT` into votes; the primary key rejects a second vote |
| 12 | Take a vote back | Transaction: room check + delete marker + `ADD vote_count -1` | `DELETE` from votes |
| 13 | My votes | `Query` on `VOTE#<user>#` | `SELECT` on index `votes_user` |
| 14 | Comment | Transaction: room check + `Put` + `ADD comment_count 1` | Lock the room `FOR SHARE`, `INSERT` |
| 15 | An idea's comments | `Query` on `COMMENT#<idea>#` | `SELECT` on index `comments_idea` |
| 16 | Close a room | Transaction: update room + delete `CODE#` item | `SELECT ... FOR UPDATE`, `UPDATE`; the code is free because the index only covers open rooms |
| 17 | My rooms | `Query` on GSI1 (eventually consistent) | `SELECT` on index `rooms_owner` (consistent) |
| 18 | Delete old rooms | TTL, free but up to days late | A scheduled `DELETE` (cron or `pg_cron`); `ON DELETE CASCADE` removes everything in the room |

## The rules

Every rule the app has is enforced by the database in both versions. In DynamoDB that's
condition expressions inside transactions (data-model section 4). In SQL most of them are
declared once in the schema:

| Rule | DynamoDB | PostgreSQL |
|---|---|---|
| Unique code among open rooms | A separate `CODE#` item, written in the same transaction as the room | `CREATE UNIQUE INDEX ... WHERE status = 'open'` |
| One vote per person per idea | The vote marker's key + `attribute_not_exists` | Primary key on votes |
| No posts, votes or comments in a closed room | `ConditionCheck` on the room in every transaction | The room is read `FOR SHARE` before each write (see Concurrency) |
| Only the owner closes a room | Condition `owner_id = :uid` | Checked after `SELECT ... FOR UPDATE` |
| The idea is in this room | The key includes the room, so a wrong room means the idea doesn't exist | Foreign key `(room_id, idea_id)` |
| Must join before posting or voting | Not checked (the web client always joins first) | Foreign key to participants, for free |
| Counters match the votes | `ADD` in the same transaction as the marker | No counters to keep in sync: a board load counts the rows |
| Expired rooms are hidden | Every read and write checks `expires_at` on the item (copied onto every item) | Reads check the room's `expires_at`; only the room has one |

`checks.sql` tests each of these, plus input limits, renaming, the cleanup and the cascade.

One difference in what's allowed: in DynamoDB a new room can take an expired room's code right
away (`expires_at < :now` in the code item's condition). A partial index's condition can't use
`now()`, so in SQL an expired room keeps its code until pattern 18 deletes it. With about 887
million possible codes that doesn't matter in practice.

## Concurrency

This is where the benchmark makes the comparison concrete.

DynamoDB has no locks. A transaction that touches an item another transaction is using is
cancelled with `TransactionConflict`, and our code retries it. Because every post, vote and
comment checks the room's `META` item, a whole class acting at once conflicts on that one item:
at 300 students, almost two thirds of votes were retried and 4% failed after five tries
([benchmark.md](benchmark.md) section 3). In the hot-idea scenario, everyone also updates the
same `vote_count`.

PostgreSQL locks rows. Each write reads the room `FOR SHARE`, and shared locks don't block each
other, so students posting and voting at the same time never wait on the room. Closing a room
takes `FOR UPDATE`, which waits until those writes commit; anything that starts after the close
sees the room closed. A vote inserts its own row, so 300 votes for one idea don't touch a shared
row either. We checked this with two `psql` sessions: while one session held a vote
transaction open, a second vote for the same idea went straight through, a close waited about
two seconds until the first session committed, and votes after that got `room_closed`.

So the rule "no votes in a closed room", which costs us thousands of conflicts in DynamoDB
(open question 3), costs SQL almost nothing. The price is elsewhere:

- **Counting on every load.** There's no stored `vote_count`, so every board load counts votes.
  Adding a counter column would bring back a hot row: `UPDATE ideas SET vote_count = vote_count
  + 1` locks the idea's row, so votes for a popular idea would queue up behind each other
  (wait, not fail, unlike DynamoDB).
- **One server.** All of this runs on one primary, with a fixed number of connections. A
  classroom is fine, but scaling to many busy classes means a bigger machine, read replicas or
  sharding by room ourselves. DynamoDB spreads rooms over partitions and on-demand capacity
  without us doing anything, which is why 10 rooms did 200-350 votes a second while one did
  65-80.
- **Locks can wait.** A long transaction holding the room `FOR SHARE` makes a close wait.
  DynamoDB's optimistic approach never waits, it fails fast and leaves retries to the client.

## What's easy in one and hard in the other

- **Easy in SQL:** questions we didn't plan for. "All ideas by one student across every room"
  is `SELECT * FROM ideas WHERE author_id = ?` (an index makes it fast). In DynamoDB it needs a
  new GSI, or a `Scan` of the whole table, which cost 567 read units against a `Query`'s 1.5 in
  the benchmark. The same goes for reports like "most active rooms this week".
- **Easy in SQL:** renaming. The name lives on the participant and is joined in, so it shows on
  old posts at once. In DynamoDB the name is copied onto each idea and comment (data-model 4.2).
- **Easy in DynamoDB:** cleanup. TTL deletes expired rooms for free with no job to run; SQL needs
  something to run `delete_expired_rooms()` on a schedule.
- **Easy in DynamoDB:** live updates. Streams give every change to a Lambda with no extra code
  in the writes. PostgreSQL has `LISTEN`/`NOTIFY` and logical replication, but we'd have to send
  the notifications from triggers or run a separate service to read changes, and push them to
  the WebSockets ourselves.
- **Easy in DynamoDB:** predictable cost per request. A board load is one `Query` whatever the
  table's size. The SQL board load's cost depends on the query planner and grows with the number
  of votes it counts.

## Limitations

We didn't run the benchmark's load scenarios against PostgreSQL because of time, so the
concurrency section is based on how PostgreSQL's locks work plus the two-session check above,
not on measured throughput. The checks run in a single session, apart from that one manual
test. PostgreSQL ran with the image's default settings in a container, not a tuned server.
