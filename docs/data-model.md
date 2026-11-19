# Data model: classroom brainstorm board

This document explains how we store the brainstorm board in DynamoDB and why we designed it this
way. The code that follows this design is in `src/brainstorm/`: `schema.py` creates the table, and
`rooms.py`, `ideas.py` and `connections.py` contain the reads and writes described below.

## The big idea

DynamoDB works best when you know your queries ahead of time, so we started by listing every
read and write the app needs (section 1) and then picked keys that make each one cheap.

We use **one table** for everything (called a *single-table design*). Every item has a
*partition key* (`PK`), which decides which group the item belongs to, and a *sort key* (`SK`),
which orders the items inside that group.

All the data for one room shares the same partition key, `ROOM#<room_id>`. A group of items with
the same partition key is called an *item collection*. Because a room's room info, ideas,
comments, votes and participants all live together, we can load a whole board with a single
`Query` instead of joining tables like we would in SQL. It also means the whole room can expire
together.

Only three things live outside the room's partition:

- **Join codes** (`CODE#<code>`). Each code gets its own item so the database can guarantee that
  two open rooms never get the same code.
- **"My rooms" for instructors.** This uses a *global secondary index* (GSI), which is a second
  copy of some of the data sorted by different keys. Ours is called GSI1.
- **Connection lookups** (`CONN#<connection_id>`). When a WebSocket closes, API Gateway only tells
  us the connection id, so this small item points back to the room (section 2).

## Naming rules we follow

- Key attributes are called `PK`, `SK`, `GSI1PK` and `GSI1SK`, and they are all strings. Key
  values start with an uppercase prefix joined with `#`, like `ROOM#abc123`.
- Timestamps are ISO 8601 in UTC and always have the same length, for example
  `2026-10-18T14:05:31.120Z` (we always include milliseconds). Because they're the same length,
  sorting them as text also sorts them by time.
- `room_id`, `idea_id` and `comment_id` are random UUIDs. For now `user_id` is made up by the
  client, since we don't have logins yet.
- Every item has an `entity_type` (like `ROOM` or `IDEA`) so we can tell items apart.
- Every item in a room has `expires_at` (a number, in seconds since 1970) copied from the room.
  DynamoDB's *Time to Live* (TTL) feature deletes items after that time, so the whole room gets
  cleaned up on its own [10].
- `status` is a reserved word in DynamoDB, so in expressions we always write it as `#status` and
  map it to the real name [13]. We picked other attribute names (`body`, `owner_id`,
  `display_name`) to avoid reserved words in the first place.

### Why the sort key order matters

Inside a room's partition, items sort alphabetically by their sort key, which gives this order:

```text
COMMENT#...  <  IDEA#...  <  META  <  USER#...  <  VOTE#...  <  WS#...
```

We use this on purpose. Asking for every sort key between `IDEA#` and `META` gives us the room
info plus all the ideas, and asking for everything up to `META` also gives us the comments. A
board load never reads participants, votes or WebSocket connections because they sort after
`META`. If we add a new kind of item to a room later, its prefix has to sort after `META` too.

## 1. What the app needs to do (access patterns)

Here is every read and write the app does, and which key it uses. "Transaction" means
`TransactWriteItems`, which lets us write several items so that either all of the writes happen
or none of them do [6].

| # | What the app does | How we do it |
|---|---|---|
| 1 | Create a room with a unique join code | Transaction: add the room item and its code item (section 4.1) |
| 2 | Look up a room from its join code | `GetItem` on `CODE#<code>` with a strongly consistent read, then reject it if it's expired |
| 3 | Get a room's info | `GetItem` on `ROOM#<id>` / `META`, then reject it if it's expired |
| 4 | Join a room | Transaction: check the room is open, then add or update the participant (4.2) |
| 5 | List the people in a room | `Query` for sort keys starting with `USER#` |
| 6 | Post an idea (open rooms only) | Transaction: check the room is open, then add the idea (4.3) |
| 7 | Load the board, newest ideas first | `Query` for sort keys between `IDEA#` and `META`, in reverse order |
| 8 | Load the board with comments | `Query` for sort keys up to `META`, in reverse order |
| 9 | Page through ideas | `Query` for sort keys starting with `IDEA#`, with a page size |
| 10 | Show the top-voted ideas | Sort the ideas from pattern 7 in the app |
| 11 | Vote for an idea (once per person) | Transaction: check the room, add a vote marker, add 1 to the count (4.4) |
| 12 | Take a vote back | Transaction: check the room, delete the marker, subtract 1 (4.5) |
| 13 | See which ideas I voted for | `Query` for sort keys starting with `VOTE#<my id>#` |
| 14 | Comment on an idea | Transaction: check the room, add the comment, add 1 to the comment count (4.6) |
| 15 | Read the comments on one idea | `Query` for sort keys starting with `COMMENT#<idea id>#` |
| 16 | Close a room | Transaction: mark the room closed and free its join code (4.7) |
| 17 | Instructor lists their rooms | `Query` on GSI1 for `USER#<owner id>`, newest first |
| 18 | Delete old rooms | Nothing to call: TTL deletes items after `expires_at` |
| 19 | Connect a WebSocket to a room | Read the room (pattern 3), then a transaction adds the connection and its lookup item (4.8) |
| 20 | Disconnect a WebSocket | `GetItem` on `CONN#<connection_id>` to find the room, then a transaction deletes both items (4.8) |
| 21 | List a room's connections (for live updates) | `Query` for sort keys starting with `WS#` |

There are no `Scan`s. A Scan reads the whole table, which gets slow and expensive as the table
grows. Every pattern above is a `GetItem` or a `Query` on one partition. A `Query` can match the
sort key with `=`, `<`, `<=`, `>`, `>=`, `BETWEEN` or `begins_with` [3].

A few things to know:

- TTL doesn't delete items right on time. It can take a few days [10]. That's why every read
  checks `expires_at` itself, and every write checks it in its condition.
- Reads from a GSI are *eventually consistent*: right after a write, the index might not show the
  change yet [9]. That's fine for an instructor's room list.
- A `Query` returns at most 1 MB at a time [2]. Our code keeps asking for the next page until
  there are no more, so big boards still load fully.

## 2. The items we store

| Item | PK | SK | Main attributes |
|---|---|---|---|
| Room (`ROOM`) | `ROOM#<room_id>` | `META` | code, topic, status (`open` or `closed`), owner_id, created_at, closed_at, expires_at |
| Join code (`ROOM_CODE`) | `CODE#<code>` | `META` | room_id, created_at, expires_at |
| Participant (`PARTICIPANT`) | `ROOM#<room_id>` | `USER#<user_id>` | display_name, joined_at, expires_at |
| Idea (`IDEA`) | `ROOM#<room_id>` | `IDEA#<created_at>#<idea_id>` | author_id, author_name, body, vote_count, comment_count, created_at, expires_at |
| Vote marker (`VOTE`) | `ROOM#<room_id>` | `VOTE#<user_id>#<idea_id>` | idea_id, idea_sk, created_at, expires_at |
| Comment (`COMMENT`) | `ROOM#<room_id>` | `COMMENT#<idea_id>#<created_at>#<comment_id>` | idea_id, author_id, author_name, body, created_at, expires_at |
| Connection (`CONNECTION`) | `ROOM#<room_id>` | `WS#<connection_id>` | connection_id, room_id, connected_at, expires_at |
| Connection lookup (`CONNECTION_LOOKUP`) | `CONN#<connection_id>` | `META` | connection_id, room_id, connected_at, expires_at |

Room items also get `GSI1PK = USER#<owner_id>` and `GSI1SK = ROOM#<created_at>#<room_id>`, which
is what puts them in the "my rooms" index.

Here's what a few items look like (numbers are shown without quotes):

```json
{"PK": "ROOM#01JAB3K9", "SK": "META", "entity_type": "ROOM",
 "GSI1PK": "USER#prof-lee", "GSI1SK": "ROOM#2026-10-18T14:00:00.000Z#01JAB3K9",
 "room_id": "01JAB3K9", "code": "K7QM4X", "topic": "Indexing strategies",
 "status": "open", "owner_id": "prof-lee",
 "created_at": "2026-10-18T14:00:00.000Z", "expires_at": 1761055200}

{"PK": "CODE#K7QM4X", "SK": "META", "entity_type": "ROOM_CODE",
 "code": "K7QM4X", "room_id": "01JAB3K9",
 "created_at": "2026-10-18T14:00:00.000Z", "expires_at": 1761055200}

{"PK": "ROOM#01JAB3K9", "SK": "USER#stu-042", "entity_type": "PARTICIPANT",
 "user_id": "stu-042", "display_name": "Roah",
 "joined_at": "2026-10-18T14:02:11.507Z", "expires_at": 1761055200}

{"PK": "ROOM#01JAB3K9", "SK": "IDEA#2026-10-18T14:05:31.120Z#01JAB4QX",
 "entity_type": "IDEA", "idea_id": "01JAB4QX", "author_id": "stu-042",
 "author_name": "Roah", "body": "Use a GSI for top-voted ideas",
 "vote_count": 3, "comment_count": 1,
 "created_at": "2026-10-18T14:05:31.120Z", "expires_at": 1761055200}

{"PK": "ROOM#01JAB3K9", "SK": "VOTE#stu-007#01JAB4QX", "entity_type": "VOTE",
 "user_id": "stu-007", "idea_id": "01JAB4QX",
 "idea_sk": "IDEA#2026-10-18T14:05:31.120Z#01JAB4QX",
 "created_at": "2026-10-18T14:06:02.004Z", "expires_at": 1761055200}

{"PK": "ROOM#01JAB3K9", "SK": "COMMENT#01JAB4QX#2026-10-18T14:07:45.300Z#01JAB5A1",
 "entity_type": "COMMENT", "comment_id": "01JAB5A1", "idea_id": "01JAB4QX",
 "author_id": "stu-007", "author_name": "Sachin", "body": "Client-side sort is enough",
 "created_at": "2026-10-18T14:07:45.300Z", "expires_at": 1761055200}

{"PK": "ROOM#01JAB3K9", "SK": "WS#Lx3fGc7NoAMCJ4w=", "entity_type": "CONNECTION",
 "connection_id": "Lx3fGc7NoAMCJ4w=", "room_id": "01JAB3K9",
 "connected_at": "2026-10-18T14:02:12.880Z", "expires_at": 1761055200}

{"PK": "CONN#Lx3fGc7NoAMCJ4w=", "SK": "META", "entity_type": "CONNECTION_LOOKUP",
 "connection_id": "Lx3fGc7NoAMCJ4w=", "room_id": "01JAB3K9",
 "connected_at": "2026-10-18T14:02:12.880Z", "expires_at": 1761055200}
```

Some choices we made:

- **Ideas and comments are their own items**, not lists stored inside the room. A single item can
  be at most 400 KB [1], and a busy room could go over that. It would also mean rewriting one
  huge item every time someone posts. We also limit idea text to 500 characters and comments to
  300.
- **The vote marker stores the idea's sort key** (`idea_sk`), so taking a vote back doesn't need
  an extra read to find the idea.
- **A connection is stored twice.** The `WS#` item lives in the room so the live-update function
  can find everyone in a room with one Query. The `CONN#` item is there because the disconnect
  event only has the connection id. We could have used a GSI on the connection id instead, but
  GSI reads are eventually consistent [9], so a quick connect-then-disconnect could miss the
  item, and every connection would cost an extra index write. Connection ids come from API
  Gateway and we don't control their format, so we reject any id containing `#`.
- **Everything copies the room's `expires_at`.** Because of that, we can't easily make a room last
  longer once it's created (we'd have to update every item in it), so we left that out for now.

## 3. Table settings

- **Name:** `BrainstormBoard` by default (you can change it with the `BRAINSTORM_TABLE` variable).
- **Keys:** partition key `PK` and sort key `SK`, both strings.
- **GSI1:** keys `GSI1PK` and `GSI1SK`. It copies only the room fields that the "my rooms" list
  shows (room_id, code, topic, status, created_at, closed_at, expires_at, entity_type). Only room
  items have `GSI1PK`, so nothing else ends up in the index. This is called a *sparse index*, and
  it keeps the index small [9], [16].
- **Billing:** *on-demand* by default, which means we pay per request and DynamoDB handles scaling
  for us [15]. Running `scripts/create_table.py --provisioned` uses *provisioned capacity*
  instead: we reserve 20 read and 20 write units for the table and 5 of each for GSI1, which fits
  inside AWS's always-free 25 units [14]. The table gets most of it because a vote writes 3 items
  in a transaction, and DynamoDB counts each item twice (once to prepare and once to commit), so
  one vote costs about 6 write units [6].
- **TTL:** turned on for `expires_at`. It has to be a number; items where it isn't are ignored
  [10].
- **Streams:** turned on with `NEW_AND_OLD_IMAGES`, so every change record includes the item
  before and after the change [12]. We'll use this for live updates. This setting can't be changed
  after the stream is created [12].

We thought about a second index (GSI2) sorted by `vote_count` to get the top-voted ideas. We
decided against it: every vote would change the index key, which costs two extra index writes on
top of the normal write [9]. Since the board load already gives us every idea, sorting them in
the app is cheaper and just as up to date.

## 4. How the writes protect the rules

We want the database itself to enforce the app's rules (like "no posts in closed rooms" or "one
vote per person"), not our code checking first and then writing. If we checked first, two
requests arriving at the same time could both pass the check. Instead, each write has a
*condition expression*, and DynamoDB only does the write if the condition is true at that moment
[7]. When we need to change several items together, we use a transaction.

In the conditions below, `:now` means the current time in epoch seconds.

**When a transaction fails.** DynamoDB tells us why with a list of reasons, one per action, in
the same order as the actions [6], [18]. A reason of `ConditionalCheckFailed` means that action's
condition was false, which tells us which rule was broken. The AWS SDK doesn't retry failed
transactions on its own [6], so `transactions.py` retries them for us, up to 5 attempts with
random, growing waits. It only retries if every failure is something that might work next time:

- `TransactionConflict`: another transaction was changing the same item at the same moment.
- `ProvisionedThroughputExceeded`: we used more than our provisioned capacity.
- `ThrottlingError`: an on-demand table is still scaling up to handle more traffic.

A failed condition is never retried, because trying again won't change the answer. Every retry
sends the same `ClientRequestToken`, so if a retry repeats a write that already went through,
DynamoDB doesn't apply it twice [6].

### 4.1 Create a room with a unique code

Join codes are 6 random characters. We left out letters and numbers that look alike (no I, L, O,
0 or 1), so the alphabet is `ABCDEFGHJKMNPQRSTUVWXYZ23456789`.

The transaction does two things:

1. Add the room item, only if no item with that key exists yet: `attribute_not_exists(PK)`.
2. Add the code item, only if the code is free: `attribute_not_exists(PK) OR expires_at < :now`.

If step 2 fails, the code is already taken, so we pick a new code and try again (up to 5 times).
The `expires_at < :now` part lets a new room reuse the code of an expired room right away,
instead of waiting days for TTL to delete the old code item [10]. When a room is closed, we
delete its code item immediately (4.7).

### 4.2 Join a room

1. Check the room: `#status = :open AND expires_at > :now`.
2. Add or update the participant with
   `SET entity_type = :pt, user_id = :u, display_name = :dn, joined_at = if_not_exists(joined_at, :ts), expires_at = :exp`.

Joining twice is fine: it just updates the display name and keeps the original `joined_at`. If
step 1 fails, the room is closed or expired.

### 4.3 Post an idea

We first read the room to get its `expires_at` (pattern 3). Then:

1. Check the room: `#status = :open AND expires_at = :exp AND expires_at > :now`.
2. Add the idea with `vote_count = 0`, `comment_count = 0` and the room's `expires_at`, using
   `attribute_not_exists(PK)`.

Checking `expires_at = :exp` makes sure the idea always gets the same expiry time as its room.
Later, we could add a third check that the poster is a participant in the room.

### 4.4 Vote

1. Check the room: `#status = :open AND expires_at > :now`.
2. Add the vote marker `VOTE#<user>#<idea>` with `attribute_not_exists(PK)`. If the person already
   voted, the marker exists and this fails, which is how we stop double voting.
3. Add 1 to the idea with `ADD vote_count :one`, only if the idea exists:
   `attribute_exists(PK)`. Without this check, voting on a missing idea would create a broken idea
   item with just a count in it [8].

`ADD` changes the number in place, so two votes at the same time can't overwrite each other's
count. This is called an *atomic counter* [8], [17]. Putting all three steps in one transaction
means the marker and the count always match [6].

### 4.5 Take a vote back

1. Check the room: `#status = :open AND expires_at > :now`.
2. Delete the vote marker, only if it exists: `attribute_exists(PK)`.
3. Subtract 1 with `ADD vote_count :minus_one`, only if
   `attribute_exists(PK) AND vote_count > :zero`.

If step 2 fails, the person hadn't voted for that idea.

### 4.6 Comment

1. Check the room: `#status = :open AND expires_at = :exp AND expires_at > :now`.
2. Add the comment with `attribute_not_exists(PK)`.
3. Add 1 to the idea's comment count with `ADD comment_count :one`, only if the idea exists.

### 4.7 Close a room

1. Mark the room closed with `SET #status = :closed, closed_at = :ts`, only if
   `owner_id = :uid AND #status = :open AND expires_at > :now`.
2. Delete the join code item, only if `attribute_not_exists(PK) OR room_id = :rid`.

The first part of step 2's condition means closing still works if TTL already deleted the code.
The second part stops us from deleting a code that a newer room is now using. That can only
happen after this room has expired, and step 1 already refuses to close an expired room, so the
two never clash. If step 1 fails, our code reads the room to tell the caller whether they aren't
the owner or the room was already closed.

### 4.8 Connect and disconnect a WebSocket

To connect, we read the room (pattern 3). If it's missing or expired we refuse with 404, and if
it's closed we refuse with 409. Then one transaction adds the `WS#` item and the `CONN#` item, so
there's never one without the other. Both items get the room's `expires_at`.

This is the one write that **doesn't** check the room inside the transaction, on purpose. A
condition check still counts as part of the transaction, and two transactions that touch the same
item at the same time conflict [6]. When a whole class opens the board at once, every connect would
fight over the room item with every other connect, and with the posts and votes happening at the
same moment. Connecting isn't a rule worth that cost: if the room closes between our read and
our write, we just store one extra connection, and that client receives `room_closed` anyway.
AWS also recommends not grouping operations in a transaction when they don't need to be [6].

To disconnect, we read `CONN#<connection_id>` with a strongly consistent read to find the room,
then delete both items in one transaction. There's no condition on the room, because a socket on a
closed or expired room still has to be cleaned up. If the lookup item isn't there, there's nothing
to do.

API Gateway only sends the disconnect event on a best-effort basis [19], so some connections are
never cleaned up this way. The live-update function deletes a connection when sending to it fails
with `GoneException`, and TTL removes whatever is left when the room expires.

## 5. Size, scale and cost

- **Item size.** Items can be up to 400 KB, including attribute names [1]. Our biggest items are
  ideas and comments, and their text is capped, so we're nowhere near that.
- **Partition limits.** Each partition is designed to handle up to 3,000 read units and 1,000
  write units per second [4]. Since a whole room lives in one partition, all of its traffic goes
  to the same place. A classroom (tens to a few hundred people) shouldn't get close to that, but
  we plan to measure it in our benchmark instead of assuming. Splitting a room across partitions
  (*write sharding* [5]) isn't worth the extra complexity unless we actually see throttling.
- **Transaction conflicts are the real risk.** If two transactions touch the same item at the same
  time, one of them gets cancelled [6]. Two items get touched a lot:
  - the room item, which every post, vote and comment checks, and
  - a popular idea's counter when lots of people vote at once.

  Our retries handle this. If the benchmark shows lots of conflicts, we could stop checking the
  room on every vote (open question 3). WebSocket connects already skip the room check for this
  reason (4.8).
- **Transactions cost double.** Each item in a transaction is processed twice (prepare and
  commit), and cancelled transactions still use capacity [6]. A vote touches 3 items.
- **The index is cheap.** GSI1 only changes when a room is created or closed, because only room
  items are in it [9].
- **TTL is free but slow.** TTL deletes don't use any write capacity, but they can happen days
  late [10], which is why we always check `expires_at` ourselves.
- **Free Tier.** The always-free 25 read and 25 write units only apply to provisioned capacity on
  the Standard table class [14]. An on-demand table is billed per request even if traffic is low.
  The free tier also includes 2.5 million stream read requests per month, and stream reads done
  by a Lambda trigger aren't charged at all [14].

## 6. Live updates with Streams (planned)

Later, a Lambda function will read the table's stream and send changes to everyone connected to
that room over a WebSocket. It will use each record's `PK` (`ROOM#<room_id>`) to find the room.

Streams only keep changes in order for each single item, not for a whole room [12]. The changes
from one transaction can also show up at different times or mixed in with other changes [6]. So
the front-end should handle each update on its own and not care if it sees the same one twice.

What we plan to send:

- **New idea** (IDEA insert): `idea_added`, with the new idea.
- **Vote count changed** (IDEA update where `vote_count` changed): `vote_count_changed`, with the
  idea id and the new count.
- **New comment** (COMMENT insert): `comment_added`. When only the idea's `comment_count` changes,
  we skip it, because the comment insert already has the data.
- **Someone joined** (PARTICIPANT insert): `participant_joined`.
- **Room closed** (ROOM update from open to closed): `room_closed`.
- **Room expired** (ROOM removed by TTL): `room_expired`. TTL deletes show up in the stream as
  deletes done by the DynamoDB service itself (`dynamodb.amazonaws.com`) [11]. We skip the TTL
  deletes for the room's other items.
- Vote markers, code items and connection items: nothing to send. Connection items change every
  time someone opens or closes the board, so the stream trigger should filter them out by
  `entity_type` instead of starting the function just to ignore them.

The function finds who to send to with pattern 21. If sending to a connection fails because it's
gone, the function deletes that connection (4.8).

A write that doesn't actually change anything doesn't create a stream record [12].

## 7. Compared to a relational database (for the report)

- **Loading a board.** In SQL we'd join rooms, ideas and comments and count votes with
  `GROUP BY`. Here it's one `Query`, and the vote count is already stored on the idea instead of
  being counted each time.
- **One vote per person.** SQL would use a primary key of `(idea_id, user_id)` on a votes table.
  We get the same effect with the vote marker key `VOTE#<user>#<idea>` and
  `attribute_not_exists`.
- **No posts in closed rooms.** SQL could use a trigger or an `INSERT ... SELECT ... WHERE
  status = 'open'` inside a transaction. We use a condition check on the room inside the
  transaction.
- **Unique codes for open rooms.** SQL could use a partial unique index on open rooms. We use a
  separate code item with a conditional write and delete it when the room closes.
- **Deleting old rooms.** SQL would need a scheduled job running `DELETE ... WHERE expires_at <
  now()`. TTL does it for free, but not right on time.
- **Questions we didn't plan for.** Something like "all ideas by one student across every room"
  is an easy query in SQL. Here we'd need a new GSI, or a Scan, which we want to avoid. This is
  the main trade-off: DynamoDB is fast and cheap for the questions you designed for, and harder
  for the ones you didn't.

## Open questions

What we're doing for now is in brackets.

1. **On-demand or provisioned?** On-demand is simpler but isn't covered by the free 25 units
   [14]. (Decided 2026-10-18: on-demand for the demo, paid with the new account's Free plan
   credits. `--provisioned` is there as a free backup option.)
2. **Logins.** Do we use real accounts (for example Amazon Cognito) or keep client-made user ids?
   (Client-made ids for now.)
3. **Votes in closed rooms.** Should voting stop when a room closes? Skipping the room check on
   votes would mean fewer conflicts. (Voting stops.)
4. **How long rooms last.** What should the default be, and can instructors extend it? Extending
   means updating every item in the room. (24 hours, can't be extended.)
5. **Editing and deleting.** Can people edit or delete their ideas and comments? That would need
   new access patterns and stream events. (Not for now.)
6. **"Rooms I've joined" for students.** We could add participant items to GSI1 with
   `GSI1PK = USER#<user>` and `GSI1SK = JOINED#<time>#<room_id>`. (Not for now.)
7. **Storing WebSocket connections.** (Decided 2026-11-18: in the room as `WS#<connection_id>`,
   plus a `CONN#<connection_id>` lookup item for disconnects; see 4.8.)

## References

[1] AWS, "Quotas in Amazon DynamoDB," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ServiceQuotas.html
[2] AWS, "Paginating table query results in DynamoDB," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html
[3] AWS, "Key condition expressions for the Query operation," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.KeyConditionExpressions.html
[4] AWS, "Best practices for designing and using partition keys effectively," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-partition-key-design.html
[5] AWS, "Using write sharding to distribute workloads evenly," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-partition-key-sharding.html
[6] AWS, "Amazon DynamoDB Transactions: How it works," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html
[7] AWS, "Condition expressions," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html
[8] AWS, "Update expressions," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.UpdateExpressions.html
[9] AWS, "Using Global Secondary Indexes in DynamoDB," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html
[10] AWS, "Using time to live (TTL) in DynamoDB," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html
[11] AWS, "DynamoDB Streams and Time to Live," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/time-to-live-ttl-streams.html
[12] AWS, "Change data capture for DynamoDB Streams," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html
[13] AWS, "Reserved words in DynamoDB," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ReservedWords.html
[14] AWS, "Amazon DynamoDB pricing" (Free Tier section), https://aws.amazon.com/dynamodb/pricing/
[15] AWS, "DynamoDB on-demand capacity mode," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html
[16] AWS, "Take advantage of sparse indexes," https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-indexes-general-sparse-indexes.html
[17] AWS, "Working with items and attributes" (Atomic counters), https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithItems.html#WorkingWithItems.AtomicCounters
[18] AWS, "TransactWriteItems," Amazon DynamoDB API Reference, https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html
[19] AWS, "$connect and $disconnect routes," https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-route-keys-connect-disconnect.html
