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

The browser client will be served from a different origin than the API, so every response
includes `Access-Control-Allow-*` headers and `OPTIONS` requests get an empty `204`. The allowed
origin is `*` unless the `CORS_ALLOW_ORIGIN` environment variable says otherwise.
