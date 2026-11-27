# Challenges and how we overcame them

The course outline asks the presentation to "discuss any challenges you faced and how you overcame
them". These are the ones we picked for it. The first five are the main talking points; the last
three are smaller and only get a line each. The report's challenges section can use all of them.

Each entry has the problem, how we fixed it, and what it taught us about DynamoDB.

## Main challenges

### 1. Business rules without check-then-write

- **Where:** `rooms.py`, `ideas.py` (one vote per user, unique join code, no posts in a closed
  room, only the owner can close it)
- **Problem:** the obvious way is to read the room, check it's open, then write. That's a race:
  the room can close, or the same student can vote again from another tab, between the read and
  the write.
- **Fix:** every rule is a condition expression inside one transaction, for example a
  `ConditionCheck` on the room (`#status = :open AND expires_at > :now`) next to the write. Join
  codes get their own `CODE#<code>` item so `attribute_not_exists(PK)` keeps them unique.
- **Takeaway:** DynamoDB has no unique constraints or foreign keys. You build them out of keys and
  conditions (see `docs/relational.md` for how PostgreSQL does the same rules).

### 2. The hot item was the room, not the partition

- **Where:** `ideas.vote`, the `hot-room` and `no-room-check` benchmark scenarios on AWS
- **Problem:** we expected the single-room partition (1,000 WCU) to be the limit. Instead a room
  topped out at about 65-80 votes/s at every class size while using about half of the
  partition's write units. At 300 students two thirds of the votes were retried and 4% failed
  after 5 attempts. The cause was the room's `META` item, which every post, vote and comment
  checks in its transaction.
- **Fix:** we measured it instead of guessing. Without the room check, vote conflicts went from
  1,688 to 16, none failed, and throughput nearly tripled. We kept the check anyway so a closed
  board can't change, and report the cost as a trade-off (`docs/benchmark.md` section 3).
- **Takeaway:** a condition check in a transaction counts as touching the item, so one item that
  every transaction checks becomes the bottleneck long before the partition's capacity does.

### 3. The benchmark measured our laptop, not DynamoDB

- **Where:** `scripts/benchmark.py`
- **Problem:** the first AWS run had every student as a thread in one Python process. Latency
  went from about 300 ms to 3 s as the class grew from 30 to 300, even when the students were
  spread over 10 rooms with almost no conflicts. Throughput was stuck at 90-150 ops/s and the
  process used one full core. Python's GIL was the bottleneck, so requests were queueing on our
  side.
- **Fix:** we threw those results out, split the students over one process per CPU, and record
  each process's CPU use in every phase, so a saturated client shows up in the results.
- **Takeaway:** check that the load generator isn't the bottleneck before trusting what its
  numbers say about the database.

### 4. Condition builders break transactions

- **Where:** `src/brainstorm/transactions.py`
- **Problem:** boto3's `Attr`/`Key` condition builders work fine with `put_item`, but inside
  `TransactWriteItems` boto3 moves their placeholders to the top level of the request, and
  DynamoDB rejects it.
- **Fix:** every transaction condition is an expression string with explicit `#name`/`:value`
  placeholders.
- **Takeaway:** the SDK's convenience layer doesn't treat every API the same way. Know what
  request actually gets sent.

### 5. SAM's stream shortcut grants every stream in the account

- **Where:** `template.yaml`, the stream Lambda
- **Problem:** SAM's `Events: Type: DynamoDB` attaches the managed
  `AWSLambdaDynamoDBExecutionRole`, which can read every DynamoDB stream in the account
  (`Resource: "*"`). Switching to a plain `AWS::Lambda::EventSourceMapping` then failed on the
  live stack: CloudFormation creates the new mapping before deleting the old one, Lambda allows
  only one mapping per stream and function, and the update rolled back (`409 AlreadyExists`).
- **Fix:** our own mapping, with the stream read actions limited to `Table.StreamArn`. On the
  existing stack we deployed once without a mapping, then with the new one (a fresh deploy
  doesn't hit this).
- **Takeaway:** shortcuts pick broad IAM defaults, so check which policy actually got attached.
  And replacing an event source mapping isn't atomic.

## Smaller challenges

### 6. TTL was much faster than documented

We planned for TTL deletes up to about 48 hours late, so the TTL evidence had to be set up days
before the recording. On AWS they came 11-17 minutes after `expires_at`
(`benchmarks/results/ttl-*`), and DynamoDB Local never deleted anything. Reads already check
`expires_at` themselves, so the board was right either way. TTL timing is best effort, so
correctness can't depend on it.

### 7. Reloading the board can undo a newer live update

A socket only gets messages sent after it opens, so the board reloads after every reconnect. A
live message can arrive while that reload is in flight, and applying the older reload last would
set a vote count back. We queue messages during a reload, send totals instead of +1s, and update
only the row the message is about (which also keeps the cursor in a comment someone is typing).
Handling stream events idempotently has to carry through to the browser too.

### 8. The same stream record has two shapes

Our TTL check found 27 REMOVE records on the stream but said none of them were TTL deletes. The
Streams `GetRecords` API spells the field `{"Type", "PrincipalId"}`, while Lambda delivers
`{"type", "principalId"}`, and our hand-written test records only had Lambda's shape.
`stream_events.from_get_records` now converts one to the other, and a real TTL record from AWS is
a test fixture. Test with at least one real record from the service, not only hand-made ones.
