# HTTP API: classroom brainstorm board

This is the API the web client talks to. All of it is one Python function,
`lambda_handler` in `src/brainstorm/api.py`. On AWS, API Gateway (an HTTP API) sends every request
to that one Lambda function, and the function picks the right route itself. We went with one
function instead of one per route because it's less to deploy, and a warm function can serve any
route without a cold start.

To run the API on your own computer, use `scripts/serve_local.py` (see the README). It turns each
request into the same event API Gateway would send, so the code we test locally is the exact code
that runs on AWS.

Each route calls one function in `rooms.py` or `ideas.py`. The pattern numbers (P1, P2, ...) are
the access patterns in section 1 of [data-model.md](data-model.md).

## Who is calling

We don't have logins yet (see open question 2 in the data model), so the client makes up a user id,
saves it in the browser, and sends it on every request in an `X-User-Id` header. A user id is 1-64
letters, digits, `_` or `-`. It can't contain `#`, because we put user ids inside keys like
`VOTE#<user_id>#<idea_id>`. A missing or bad id gets `401 missing_user`.

Anyone can read a room if they know its id, so most read routes don't need the header. Every
write route needs it, and so do `/my-rooms` and `/my-votes`, since they answer "what's mine".

Because nobody checks the header, a room's owner id is all you need to close it. That's why
responses never include `owner_id`: otherwise any student with the join code could read it and
close the room. The owner's client already knows which rooms are its own from `POST /rooms` and
`/my-rooms`. This is only a weak protection until we have real logins. Someone who guesses the
owner's id (demo ids like `prof` are easy to guess) can still close the room, and anyone can send
another student's id to post or vote as them.

## Routes

Request and response bodies are JSON. Responses never include our internal key attributes (`PK`,
`SK`, `GSI1PK`, `GSI1SK`) or a room's `owner_id`. The one exception is that every idea comes back with an `idea_sk`
field, which is the idea's sort key (`IDEA#<created_at>#<idea_id>`). The vote and comment routes
use `idea_sk` to find the idea, so they can update it without looking it up first. Because it
contains `#` and `:`, the client has to percent-encode it in the URL (`encodeURIComponent` in
JavaScript).

| Method and path | Body | Success | Pattern |
|---|---|---|---|
| `POST /rooms` | `{"topic"}` | `201` the room | P1 |
| `GET /my-rooms` | | `200 {"rooms": [...]}`, newest first | P17 |
| `GET /codes/{code}` | | `200` the room (code is not case-sensitive) | P2, P3 |
| `GET /rooms/{room_id}` | | `200 {"room", "ideas", "comments"}` | P7, P8 |
| `POST /rooms/{room_id}/join` | `{"display_name"}` | `200` the participant | P4 |
| `GET /rooms/{room_id}/participants` | | `200 {"participants": [...]}` | P5 |
| `POST /rooms/{room_id}/close` | | `204` (room owner only) | P16 |
| `POST /rooms/{room_id}/ideas` | `{"display_name", "body"}` | `201` the idea | P6 |
| `GET /rooms/{room_id}/ideas` | | `200 {"ideas", "cursor"}` | P9 |
| `PUT /rooms/{room_id}/ideas/{idea_sk}/vote` | | `204` | P11 |
| `DELETE /rooms/{room_id}/ideas/{idea_sk}/vote` | | `204` | P12 |
| `GET /rooms/{room_id}/my-votes` | | `200 {"idea_ids": [...]}` | P13 |
| `POST /rooms/{room_id}/ideas/{idea_sk}/comments` | `{"display_name", "body"}` | `201` the comment | P14 |
| `GET /rooms/{room_id}/ideas/{idea_sk}/comments` | | `200 {"comments": [...]}`, oldest first | P15 |

Some notes on these:

- **Loading the board.** `GET /rooms/{room_id}` returns the room and all its ideas, newest first,
  from a single `Query`. Add `?comments=true` to get the comments too, grouped by idea id. The
  client sorts by `vote_count` itself to show the top ideas (P10).
- **Paging.** `GET /rooms/{room_id}/ideas` takes `?limit=` (1-100, default 20). If there are more
  ideas, the response has a `cursor`. Send it back as `?cursor=` to get the next page. The cursor
  is just DynamoDB's `LastEvaluatedKey` in base64, and the server checks that it belongs to the
  same room before using it, so a made-up cursor can't read another room.
- **Display names** are sent with each idea and comment, because those items store the author's
  name. That way loading the board doesn't need a second lookup for names.
- **Text limits.** A topic is at most 200 characters, a display name 50, an idea 500 and a comment
  300. Leading and trailing spaces are trimmed, and empty text is rejected.

## Errors

Errors come back as `{"error": "<code>", "message": "<details>"}`.

| Status | `error` | When |
|---|---|---|
| 400 | `invalid_input` | Missing or too-long field, bad JSON, bad `limit` or `cursor` |
| 401 | `missing_user` | Missing or bad `X-User-Id` on a write |
| 403 | `not_room_owner` | Someone other than the owner tried to close the room |
| 404 | `not_found` | No such route |
| 404 | `room_not_found` | The room or code doesn't exist, or the room has expired |
| 404 | `idea_not_found` | No such idea in this room |
| 409 | `room_closed` | Writing to a closed room |
| 409 | `already_voted` / `not_voted` | Voting twice, or taking back a vote you never gave |
| 503 | `code_unavailable` | We couldn't find a free join code after 5 tries |
| 503 | `busy` | DynamoDB is throttling us, or a transaction kept conflicting after our retries |
| 500 | `internal_error` | A bug. The details are logged and never sent to the client |

Most of the 409s come straight from DynamoDB condition expressions. For example, when a vote's
transaction fails because the vote marker already exists, the data layer turns that into
`AlreadyVotedError` and the API returns `already_voted`. The database enforces the rule, and the
API only translates the result.

The `busy` error is the one to watch in our benchmark. Every write to a room checks the room's
`META` item inside a transaction, so a lot of students voting at once can cause transaction
conflicts. `transact_write` retries those with backoff, and `busy` means it still failed after
5 tries.

## CORS

The web client is served from a different origin than the API, so every response
includes `Access-Control-Allow-*` headers and `OPTIONS` requests get an empty `204`. The allowed
origin is `*` unless the `CORS_ALLOW_ORIGIN` environment variable says otherwise.
On AWS, `template.yaml` sets it to the CloudFront URL of the web client, so only our own page
can call the API from a browser. API Gateway's own CORS setting is off, because the handler
already answers `OPTIONS` and both would set the same headers.

## WebSocket API (live updates)

The board updates live over a WebSocket. This is a second API Gateway API (a WebSocket API, not
an HTTP API), and it runs `lambda_handler` in `src/brainstorm/ws.py`. API Gateway keeps the socket
open and only calls our function when a client connects, disconnects or sends a message, so the
function doesn't have to stay running for the whole class.

To subscribe to a room, the client opens:

```
wss://<api-id>.execute-api.<region>.amazonaws.com/<stage>?room_id=<room_id>
```

The room id goes in the query string because browsers can't set headers on a WebSocket. There's
no `X-User-Id` here: watching a board is a read, and anyone with the room id can already read it.

| Route | What we do | Pattern |
|---|---|---|
| `$connect` | Store the connection for the room, or refuse it | 19 |
| `$disconnect` | Delete the connection's items | 20 |
| `$default` | Nothing. Clients never send us anything we act on | |

`$connect` refuses the socket by returning a status other than 200:

| Status | When |
|---|---|
| 400 | `room_id` is missing, empty, contains `#`, or is over 128 characters |
| 404 | The room doesn't exist or has expired |
| 409 | The room is closed |
| 503 | DynamoDB is busy (throttling or transaction conflicts) |
| 500 | A bug. The details are logged |

A browser doesn't show the client which status it got. The socket just fails to open. So when
that happens, the client should load the board over HTTP (`GET /rooms/{room_id}`) to find out why,
and show "room closed" or "not found" from that response.

`$disconnect` is best effort. API Gateway doesn't promise to send it, for example when a laptop
loses Wi-Fi. A connection that never got cleaned up is removed when a send to it fails with
`GoneException`, or by TTL when the room expires. Section 4.8 of [data-model.md](data-model.md)
explains how connect handles a room that closes at the same moment.

The deployed URL is the `WebSocketUrl` output of the stack (the stage is `prod`). API Gateway
WebSockets don't run on your own computer, so locally `scripts/serve_local.py` starts a stand-in
at `ws://127.0.0.1:3001/?room_id=<room_id>` (`scripts/live_local.py`). It runs the same
`ws.handle` for connect and disconnect, so it refuses sockets with the same statuses and stores
connections the same way. A browser sees the same messages from both.

### Messages

Updates only go from the server to the client. Each message is one JSON object with a `type` and
the `room_id` it belongs to. They're built from DynamoDB Streams records by `to_event` in
`src/brainstorm/stream_events.py`; section 6 of [data-model.md](data-model.md) says which table
changes become which message.

| `type` | Sent when | Other fields |
|---|---|---|
| `idea_added` | Someone posts an idea | `idea`: the idea, same shape as in the HTTP API (with `idea_sk`) |
| `vote_count_changed` | An idea's vote count goes up or down | `idea_id`, `idea_sk`, `vote_count` (the new total) |
| `comment_added` | Someone comments on an idea | `comment`: the comment, same shape as in the HTTP API |
| `participant_joined` | Someone joins the room for the first time | `participant`: the participant, same shape as in the HTTP API |
| `room_closed` | The owner closes the room | `closed_at` |
| `room_expired` | DynamoDB's TTL deletes the room | |

```json
{"type": "idea_added", "room_id": "01JAB3K9",
 "idea": {"entity_type": "IDEA", "idea_id": "01JAB4QX",
          "idea_sk": "IDEA#2026-10-18T14:05:31.120Z#01JAB4QX",
          "author_id": "stu-042", "author_name": "Roah", "body": "Use a GSI for top-voted ideas",
          "vote_count": 0, "comment_count": 0,
          "created_at": "2026-10-18T14:05:31.120Z", "expires_at": 1761055200}}

{"type": "vote_count_changed", "room_id": "01JAB3K9", "idea_id": "01JAB4QX",
 "idea_sk": "IDEA#2026-10-18T14:05:31.120Z#01JAB4QX", "vote_count": 3}

{"type": "comment_added", "room_id": "01JAB3K9",
 "comment": {"entity_type": "COMMENT", "comment_id": "01JAB5A1", "idea_id": "01JAB4QX",
             "author_id": "stu-007", "author_name": "Sachin", "body": "Client-side sort is enough",
             "created_at": "2026-10-18T14:07:45.300Z", "expires_at": 1761055200}}

{"type": "participant_joined", "room_id": "01JAB3K9",
 "participant": {"entity_type": "PARTICIPANT", "user_id": "stu-042", "display_name": "Roah",
                 "joined_at": "2026-10-18T14:02:11.507Z", "expires_at": 1761055200}}

{"type": "room_closed", "room_id": "01JAB3K9", "closed_at": "2026-10-18T15:00:00.000Z"}

{"type": "room_expired", "room_id": "01JAB3K9"}
```

Like HTTP responses, messages never include `PK`, `SK`, `GSI1PK`, `GSI1SK` or `owner_id`. A new
comment doesn't send a separate message for the idea's `comment_count`: the client adds 1 itself
when it gets `comment_added`.

What the client has to handle:

- **Duplicates and order.** DynamoDB Streams can deliver a change twice, and changes to different
  items (an idea and its comment, say) can arrive in any order. So each message carries absolute
  values (`vote_count` is the new total, not +1), and the client should skip an idea, comment or
  participant it already has (by `idea_id`, `comment_id` or `user_id`). A `comment_added` can
  arrive before its `idea_added`; the client should keep it until the idea shows up or reload the
  board.
- **Missed messages.** A message sent while the socket was reconnecting is lost. After
  reconnecting, the client reloads the board over HTTP.
- **End of the board.** `room_closed` and `room_expired` mean nothing more will change. The
  client shows the room as closed. The server closes the socket right after sending either one,
  so the client shouldn't try to reconnect.
- **Unknown types.** Ignore any `type` not listed here, so we can add messages later.
