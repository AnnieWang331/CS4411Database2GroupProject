# CS4411Database2GroupProject

## Classroom Brainstorm Board in Real-Time using Amazon DynamoDB

Group project for **COMPSCI 4411/9538 (Databases II)** at Western University, Fall 2026, in the
_In-Depth Analysis of Data Management Systems_ category (Amazon DynamoDB, Group 20).

### Overview

Relational databases can struggle when an application needs to manage large amounts of rapidly
changing data at scale. Amazon DynamoDB is a fully managed, serverless NoSQL key-value database
built for this problem. It offers automatic scaling, high availability, and low-latency access
for predictable access patterns.

To demonstrate DynamoDB, we built a **live, collaborative brainstorm board**:

- An instructor creates a room for a topic.
- Students join the room with a code and post ideas.
- Everyone in the room sees the board update in real time.

Every action in the app (creating a room, posting an idea, loading the board) is simple and known
ahead of time, which makes it a good fit for DynamoDB's data modelling. The project showcases:

- **Single-query board loads.** Each room's data is stored together, so one query returns the whole board.
- **Conditional writes** that enforce application rules inside the database itself.
- **Time to Live (TTL)** that deletes old rooms automatically.
- **DynamoDB Streams** that push live updates to connected users.
- **Serverless scaling** from one classroom to many, with no servers to manage.

### Objectives

- Gain a practical understanding of DynamoDB's architecture (design principles, data flow, and
  scalability) and its main features (data storage, retrieval and updates, query patterns, and security).
- Build a working idea board where users can create, share, and manage ideas and interact with
  other users' ideas, for example by voting or commenting.
- Evaluate the advantages and disadvantages of DynamoDB and how it differs fundamentally from a
  traditional relational SQL database.

### Deliverables

- Project proposal (submitted November 4, 2026; see
  [the proposal](docs/project-info/cs4411-group-20-project-proposal.pdf))
- Final report (LaTeX, in the course template's style; source in [`report/`](report/README.md))
- 15-minute recorded group presentation with slides and a live demo
- Complete project artifacts for reproducibility: source code, datasets, and supporting materials

Final deadline: **December 6, 2026**

The course's project outline, the peer-review rubric and our proposal are in
[docs/project-info/](docs/project-info/).

## Running the project locally

You can run everything on your own computer using **DynamoDB Local**, a free version of DynamoDB
from AWS that runs on your machine. You don't need an AWS account for any of the steps below.

### What you need

- Python 3.12 or newer
- Docker or Podman (we use it to run DynamoDB Local, and PostgreSQL for the comparison)

On Windows, read the next section first.

### On Windows

The commands in this README are for a Linux or macOS terminal. On Windows you have two options.

**Option 1: WSL (recommended).** WSL runs Ubuntu inside Windows, so every command below works as
written. Docker Desktop needs WSL anyway.

1. Open PowerShell as administrator, run `wsl --install`, and restart. Open "Ubuntu" from the
   Start menu and pick a username and password.
2. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/). In its settings,
   under Resources > WSL integration, turn it on for Ubuntu. If Docker says virtualization is
   off, turn on "Intel VT-x" or "AMD-V"/"SVM" in your computer's BIOS settings.
3. In the Ubuntu window, install Python's venv module with
   `sudo apt update && sudo apt install -y python3-venv python3-pip`.
4. Clone or unzip the project inside Ubuntu (for example in `~`, not under `/mnt/c`, which is
   much slower), then follow the steps below. Use `python3` wherever this README says `python`
   until you've turned on the virtual environment. Your Windows browser can open the
   `http://127.0.0.1:...` addresses.

**Option 2: PowerShell.** Everything except the PostgreSQL comparison (step 9) also works
without Docker. These are the differences:

- **Python**: install it from [python.org](https://www.python.org/downloads/windows/) and tick
  "Add python.exe to PATH" on the first screen of the installer. If typing `python` opens the
  Microsoft Store, use `py` instead, or turn off the `python.exe` entries under Settings > Apps >
  Advanced app settings > App execution aliases.
- **Virtual environment**: PowerShell blocks the activate script by default, so allow it once
  first:

  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  py -m venv .venv
  .venv\Scripts\Activate.ps1
  ```

- **DynamoDB Local without Docker**: install Java 17 or newer (for example
  [Temurin](https://adoptium.net/)), download
  [DynamoDB Local](https://d1ni2b6xgvw0s0.cloudfront.net/v3.x/dynamodb_local_latest.zip), unzip
  it, and start it from the unzipped folder. Keep that window open; this replaces step 2.

  ```powershell
  java "-Djava.library.path=./DynamoDBLocal_lib" -jar DynamoDBLocal.jar -inMemory -sharedDb
  ```

- **Settings**: `export NAME=value` becomes `$env:NAME = "value"`. It only lasts for that
  PowerShell window, so set `DYNAMODB_ENDPOINT_URL` again in every new window (for example the
  second terminal in steps 6 and 7):

  ```powershell
  $env:DYNAMODB_ENDPOINT_URL = "http://localhost:8000"
  $env:REQUIRE_DYNAMODB_LOCAL = "1"; pytest
  ```

- **Long commands**: put commands that end in `\` on one line (or end the lines in a backtick
  `` ` `` instead).
- **curl**: in Windows PowerShell, `curl` isn't the real curl and mangles the JSON. Use
  `Invoke-RestMethod` instead:

  ```powershell
  Invoke-RestMethod -Method Post -Headers @{"X-User-Id" = "prof"} -Body '{"topic": "Indexing"}' `
    -Uri http://127.0.0.1:3000/rooms
  ```

- **Benchmark**: Windows has no `fork`, so `benchmark.py` runs every student in one process.
  It works, but local throughput is lower than on Linux or macOS.
- **Port 8000**: if DynamoDB Local says the port is in use or access is forbidden (Windows
  sometimes reserves it), use another port as in step 2.

GitHub Actions runs these PowerShell steps on Windows on every pull request (the `test-windows`
job in `.github/workflows/ci.yml`).

### 1. Install the Python packages

Clone the repository, or unzip the submitted archive, and run every command below from its top
folder (the one with this README). Nothing needs git.

Make a virtual environment and turn it on. For example, run `python -m venv .venv` and then
`source .venv/bin/activate` (in PowerShell, see "On Windows" above; a pyenv virtualenv works
too). Then install the packages:

```sh
pip install -r requirements-dev.txt
```

This installs boto3 (the AWS library for Python), websockets (for live updates on your own
computer) and matplotlib (for the benchmark charts), plus pytest, ruff and cfn-lint, which we use
for testing and linting.

### 2. Start DynamoDB Local

```sh
docker run -d --rm --name dynamodb-local -p 8000:8000 amazon/dynamodb-local \
  -jar DynamoDBLocal.jar -inMemory -sharedDb
```

If you use Podman, change `docker` to `podman` and use `docker.io/amazon/dynamodb-local` as the
image name. Because of `-inMemory`, all the data disappears when the container stops, which is
handy for testing. To stop it, run `docker stop dynamodb-local`.

If something else already uses port 8000, use `-p 8001:8000` instead (or add `-port 8001` to the
`java` command on Windows) and `http://localhost:8001` wherever this README says
`http://localhost:8000`.

### 3. Create the table and add demo data

```sh
export DYNAMODB_ENDPOINT_URL=http://localhost:8000
python scripts/create_table.py
python scripts/seed.py
```

The first line points our scripts at DynamoDB Local instead of AWS.

`create_table.py` creates our `BrainstormBoard` table. It also sets up a secondary index (GSI1)
for listing an instructor's rooms, turns on DynamoDB Streams (which the live updates read from),
and turns on Time to Live (TTL) so old rooms delete themselves. If you want to start over, add
`--recreate` to delete the local table and make it again.

By default the table uses on-demand billing, where AWS charges per request. If you add
`--provisioned`, it reserves 20 read and 20 write units for the table and 5 of each for the index
instead. That stays inside the 25 units AWS gives you for free.

`seed.py` makes a demo room with a few students, ideas, votes and comments, and prints the board
so you can see it worked.

### 4. Run the tests

```sh
REQUIRE_DYNAMODB_LOCAL=1 pytest
```

The tests make their own tables in DynamoDB Local and delete them afterwards. They use
`DYNAMODB_ENDPOINT_URL` from step 3 (`http://localhost:8000` if it isn't set). With
`REQUIRE_DYNAMODB_LOCAL=1`, a test that can't reach DynamoDB Local fails. Without it, those
tests are skipped, so a run with only skips doesn't mean the tests passed. Every test should
pass, with none skipped.

Lint: run `ruff format --check .`, `ruff check .` and `cfn-lint template.yaml` before you push.
The ruff settings (like our 100-character line length) are in `pyproject.toml`.

GitHub Actions runs the same lint and tests (against DynamoDB Local) on every pull request and on
every push to `main`; see `.github/workflows/ci.yml`. In CI a test that can't reach DynamoDB Local
fails instead of being skipped. Please wait for the checks to pass before you merge.

### 5. Run the API

```sh
python scripts/serve_local.py
```

This starts our HTTP API at `http://127.0.0.1:3000` (use `--port` to change it), using the table
from step 3. On AWS the same code runs as a Lambda function behind API Gateway. The local server
just turns each request into the event Lambda would get. You can try it with curl:

```sh
curl -X POST -H 'X-User-Id: prof' -d '{"topic": "Indexing"}' http://127.0.0.1:3000/rooms
curl http://127.0.0.1:3000/codes/<code from the reply>
```

Every route and error code is listed in [docs/api.md](docs/api.md).

### 6. Watch live updates

`serve_local.py` also starts the live updates, on `ws://127.0.0.1:3001` (use `--ws-port` to
change it, or `--no-live` to turn them off). On AWS, API Gateway holds the WebSockets and a
Lambda function reads the table's stream. Neither of those runs on your computer, so
`scripts/live_local.py` does both jobs: it runs a small WebSocket server, and it reads DynamoDB
Local's stream every 0.2 seconds. It calls the same `$connect`/`$disconnect` code and the same
broadcaster as AWS. The only difference is the last step: it writes to its own sockets instead
of calling API Gateway.

Open a WebSocket on a room (with [wscat](https://github.com/websockets/wscat), which needs
Node.js, or `python -m websockets`), then post an idea from a second terminal:

```sh
python -m websockets 'ws://127.0.0.1:3001/?room_id=<room_id>'
curl -X POST -H 'X-User-Id: stu' -d '{"display_name": "Ann", "body": "Hi"}' \
  http://127.0.0.1:3000/rooms/<room_id>/ideas
```

An `idea_added` message shows up right away. Votes, comments, joins and closing the room send
messages too (see [docs/api.md](docs/api.md#messages)). A room that doesn't exist or is closed
refuses the socket, the same as on AWS.

The poller only sends changes made after it started. If you run `create_table.py --recreate`,
restart `serve_local.py` too, since the new table has a new stream.

### 7. Open the web client

The web client is plain HTML, CSS and JavaScript in `web/`, so there's nothing to build or
install. Keep `serve_local.py` running and serve the folder from a second terminal:

```sh
python -m http.server 8080 -b 127.0.0.1 -d web
```

Open <http://127.0.0.1:8080/#/host> to start a room. You get a join code to put on the
projector, a list of your rooms, and a button to close each one. The browser makes up a user id
the first time and keeps it in `localStorage`, so your rooms are still there after a reload.
Another browser (or a private window) counts as a different person.

To try it as a student, open <http://127.0.0.1:8080/> in a private window and type the code. Pick a
name, then post ideas, vote and comment. Sort the board by newest or top voted. Open the same
room in two windows: an idea, vote or comment in one shows up in the other without refreshing,
and the projector view counts people as they join. The board says "Live" while it's connected.
If `serve_local.py` stops, it says "Reconnecting…" and loads the board again once it's back.
Once the instructor closes the room, the board stays readable but nothing can be added. "Open
board" on the projector view shows the same board to the instructor.

`web/config.js` says where the APIs are. It points at `serve_local.py`'s ports, so you only need
to change it if you used `--port` or `--ws-port`.

### 8. Run the benchmark

`scripts/benchmark.py` plays a class: every student joins, posts, votes and comments at the
same moment, one phase at a time. It makes its own table (`bench-<run id>`), so
your demo data isn't touched, and deletes it afterwards (`--keep-table` keeps it):

```sh
python scripts/benchmark.py run                       # 30, 100 and 300 students, about 5 minutes
python scripts/benchmark.py run --students 30 --scenarios hot-room,hot-idea   # a quick one
```

It prints a table per scenario and operation (median/95th/99th percentile latency, operations
per second, transaction conflicts, throttles, capacity used) and checks that no vote or comment
was lost. Everything goes to `benchmarks/results/bench-<run id>-*.csv`. The scenarios are:

- `hot-room`: the whole class in one room, so all its traffic goes to one partition.
- `many-rooms`: the same students and actions spread over 10 rooms.
- `no-room-check`: like `hot-room`, but votes don't check the room in their transaction (open
  question 3 in [docs/data-model.md](docs/data-model.md)), to see how many conflicts that check
  causes.
- `hot-idea`: everyone votes for the same idea at the same moment.
- `query-vs-scan`: loading one board with a Query versus scanning the whole table.

With `serve_local.py` running, `live` measures how long a live update takes to arrive: it posts
ideas and votes over HTTP and times when the message reaches a WebSocket:

```sh
python scripts/benchmark.py live
```

`scripts/bench_charts.py` draws the report's charts from saved CSVs. It needs no database, so
this redraws the charts in `benchmarks/charts/` from our AWS runs, without an AWS account:

```sh
python scripts/bench_charts.py --run 20261126T024200Z --provisioned-run 20261126T024530Z \
  --live-run 20261126T024546Z
```

For your own run, add `--out` so the report's charts aren't overwritten:
`python scripts/bench_charts.py --run <run id> [--live-run <run id>] --out my-charts`. A run
without the `query-vs-scan` scenario skips that chart.

The students are split over one process per CPU (threads inside each), because one Python
process can't send more than about 100-150 requests a second. `--processes N` changes that; the
`client_cpu_max` column in `-phases.csv` shows if a process was still the bottleneck.

DynamoDB Local is one Java process with no partitions, throttling or network, so its numbers
only show that the code works under load. The numbers in our report come from AWS (see below).
Local also gets slower after several runs (each one creates and deletes a table); restart it
(`docker restart dynamodb-local`, then `create_table.py` and `seed.py` again) before a run.

### 9. Run the relational baseline

`sql/` has the same board as a PostgreSQL schema, for comparing the two designs. It doesn't need
Python or DynamoDB Local, only a container. Start PostgreSQL 18 with the `sql/` folder mounted
(`:Z` is for SELinux, as on Fedora; Docker on macOS or Windows doesn't need it):

```sh
docker run -d --rm --name brainstorm-postgres -e POSTGRES_PASSWORD=postgres \
  -v "$PWD/sql:/sql:ro,Z" postgres:18
docker exec brainstorm-postgres pg_isready -h 127.0.0.1 -U postgres   # until "accepting connections"
```

Then load the schema and the access patterns, run the checks, and add the demo room:

```sh
docker exec brainstorm-postgres psql -X -q -U postgres -v ON_ERROR_STOP=1 \
  -f /sql/schema.sql -f /sql/queries.sql -f /sql/checks.sql -f /sql/demo.sql
```

It prints `ok: ...` for each rule the database rejected, `all checks passed`, and the demo board
(the same one `seed.py` makes). Running it again starts from an empty schema. To try the
functions yourself, open `docker exec -it brainstorm-postgres psql -U postgres` and run
`SET search_path = brainstorm;` first. [docs/relational.md](docs/relational.md) compares the two
designs. `docker stop brainstorm-postgres` removes the container.

### Data

There is no external dataset. All the data is made by our scripts:

- **Demo board**: `scripts/seed.py` writes it. The topic, students, ideas, votes and comments are
  written out in the script, so every run makes the same board (only the room id and join code
  are new each time). `sql/demo.sql` makes the same board in PostgreSQL.
- **Benchmark results**: `benchmarks/results/bench-<run id>-*.csv` (plus a `-run.json` with the
  settings, Python and boto3 versions). The report's numbers come from three runs against AWS
  in ca-central-1: `20261126T024200Z` (`benchmark.py run`, on-demand), `20261126T024530Z`
  (`run --provisioned`) and `20261126T024546Z` (`live`). The students' actions are random with
  a fixed seed (`--seed`, 4411 by default), so a rerun sends the same requests, but its timings
  will differ. [docs/benchmark.md](docs/benchmark.md) explains how we measured and what we
  found.
  Your own runs are saved in the same folder under a new run id.
- **Charts**: `benchmarks/charts/*.png`, drawn from those three runs by `bench_charts.py` (step 8).
- **TTL results**: `benchmarks/results/ttl-20261124T213237Z-*` and `ttl-20261127T011549Z-*`,
  from two runs of `scripts/ttl_demo.py` on AWS (see "Show TTL deleting rooms" below).
  Console and terminal screenshots of the second run are in
  `benchmarks/screenshots/ttl-20261127T011549Z/`.
- **Demo evidence**: `benchmarks/screenshots/demo-20261127/`, from the deployed stack: the
  instructor and student screens, the room's items, the three actions the database rejects
  (vote twice, non-owner close, post after close), and one stream record next to the live
  message it became.

### Settings

Our code reads these environment variables:

- `DYNAMODB_ENDPOINT_URL`: where DynamoDB is. Set it to `http://localhost:8000` for DynamoDB
  Local. Leave it unset to use real AWS.
- `BRAINSTORM_TABLE`: the table name. The default is `BrainstormBoard`.
- `WEBSOCKET_ENDPOINT`: only for the live-update function on AWS. It's the WebSocket API's
  connection URL, `https://<api-id>.execute-api.<region>.amazonaws.com/<stage>`.
- `CORS_ALLOW_ORIGIN`: which website is allowed to call the API from a browser. The default is
  `*` (any site).
- `AWS_PROFILE` and `AWS_REGION`: which AWS account and region to use. These only matter when
  you're using real AWS.

To check that your AWS profile can reach DynamoDB, run `python scripts/check_aws.py`.

### Where things are

```text
docs/data-model.md     How we store the data in DynamoDB, and why
docs/api.md            The HTTP and WebSocket APIs: routes, errors, live-update messages
docs/benchmark.md      What the classroom load benchmark measured, and what it means
docs/relational.md     The same board in PostgreSQL, compared pattern by pattern
docs/challenges.md     Challenges we hit and how we got past them (for the presentation)
docs/project-info/     Course requirements: project outline, grading rubric and our proposal
template.yaml          The AWS deployment (SAM): table, HTTP and WebSocket APIs, live-update
                       function, web hosting
samconfig.toml         Settings for `sam deploy` (stack name, region)
src/brainstorm/        The Python code that talks to DynamoDB
  db.py                Connects to the table (DynamoDB Local or AWS)
  keys.py              Builds the PK/SK key values, ids, join codes and timestamps
  errors.py            The errors our code raises (room closed, already voted, ...)
  schema.py            Creates the table
  rooms.py             Creating, joining, closing and listing rooms
  ideas.py             Posting ideas, loading the board, voting, commenting
  connections.py       Which WebSockets are connected to each room
  transactions.py      Writes that change several items at once, with retries
  api.py               The HTTP API (one Lambda handler for every route)
  ws.py                The WebSocket API ($connect and $disconnect)
  stream_events.py     Turns DynamoDB Stream records into live-update messages
  broadcast.py         Sends those messages to everyone connected to the room
web/                   The web client (plain HTML, CSS and JavaScript, no build step)
  index.html           The one page; the scripts below fill it in
  config.js            Where the HTTP and WebSocket APIs are
  css/style.css        The styles (colours and sizes are at the top)
  js/app.js            Picks the screen to show from the URL (#/, #/room/..., #/host)
  js/api.js            Calls the HTTP API and keeps this browser's user id
  js/dom.js            Small helpers for building the page
  js/host.js           Instructor screens: start a room, show its code, close it
  js/student.js        Student screens: join by code, then post, vote and comment
  js/live.js           The live-update WebSocket (reconnects, keepalive, reload on reconnect)
scripts/               Scripts to create the table, add demo data, run the API and live
                       updates locally (live_local.py), check AWS access, show TTL
                       deleting rooms (ttl_demo.py), upload the web client (deploy_web.py),
                       run the benchmark (benchmark.py) and draw its charts (bench_charts.py)
sql/                   The same board in PostgreSQL, for the relational comparison
                       (schema, one function per access pattern, checks, demo data)
benchmarks/results/    Measurements we ran, as CSV: TTL delete delays and benchmark runs
benchmarks/charts/     The benchmark charts for the report
report/                The final report (LaTeX); report/README.md says how to build the PDF
tests/                 Our tests (most run against DynamoDB Local; tests/infra checks
                       template.yaml)
```

### Resources

- [DynamoDB User Guide](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html)
- [Working with DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithDynamo.html)

## Deploying to AWS

You only need this part for the live demo on phones. Everything above works without AWS.

We use **AWS SAM** (Serverless Application Model) for the deployment. SAM is a CloudFormation
extension for Lambda functions and API Gateway, so the whole stack is one file,
[`template.yaml`](template.yaml), and one command to create or delete it. We picked it over CDK
because our backend is Python Lambdas plus one table, and SAM needs no extra language or build
setup for that.

The template creates:

- the `BrainstormBoard` table, with the same keys, GSI1, Streams and TTL as `create_table.py`
  (a test checks they match). It uses on-demand billing and is encrypted at rest with an AWS
  owned key (DynamoDB's default, set explicitly with `SSESpecification`). We didn't use a KMS key
  because it costs money per request and we don't need to control or audit the key ourselves.
- an API Gateway HTTP API that sends every request to one Lambda function running
  `brainstorm.api.lambda_handler`, the same code as `serve_local.py`. That function's IAM role
  can only use the DynamoDB actions our code needs, on this table and GSI1.
- an API Gateway WebSocket API for live updates. Its `$connect`, `$disconnect` and `$default`
  routes go to a Lambda function running `brainstorm.ws.lambda_handler`.
- the live-update function (`brainstorm.broadcast.lambda_handler`), which reads the table's
  stream and sends each change to the room's open WebSockets. It gets small batches as soon as
  records arrive, since latency matters more than throughput here, and changes that never become
  a message (connections, vote markers, join codes) are filtered out before it runs. A record that keeps failing is
  split from its batch, retried 3 times, then reported to an SQS queue (`StreamFailuresQueueUrl`)
  so it can't hold up the rest of the stream. Its IAM role can only read this table's stream,
  query and delete items in the table, and send to this WebSocket API.
- a private S3 bucket and a CloudFront distribution that serve the web client over HTTPS.
  `CORS_ALLOW_ORIGIN` is set to that CloudFront URL, so other websites can't call the API.
- optionally, a monthly cost budget that emails you at 80% of the limit.

### What you need

- An AWS account and a profile that can create these resources
- The [SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
  (`pip install aws-sam-cli` works too) and the AWS CLI

### Deploy

```sh
export AWS_PROFILE=<your-profile>
sam build
sam deploy --parameter-overrides BudgetEmail=you@example.com
```

The settings are in `samconfig.toml`: the stack is called `brainstorm-board` and goes in
`ca-central-1`. `sam deploy` shows you the changes and asks before it applies them. The first
deploy takes a few minutes, mostly for CloudFront. Leave out `--parameter-overrides` if you don't
want the budget (AWS asks you to confirm the email first). `BudgetLimitUsd=10` changes the limit,
which is 5 USD by default.

When it finishes, it prints the outputs. `ApiUrl` is the API, `WebSocketUrl` is for live updates
and `WebUrl` is the web client. You can see them again with:

```sh
aws cloudformation describe-stacks --stack-name brainstorm-board \
  --query 'Stacks[0].Outputs' --output table
```

Try the API the same way as locally:

```sh
curl -X POST -H 'X-User-Id: prof' -d '{"topic": "Indexing"}' <ApiUrl>/rooms
```

Opening `ApiUrl` itself in a browser only gives a `not_found` error, because the API has no page
at `/`. Use a route from [docs/api.md](docs/api.md), like `<ApiUrl>/codes/<code>`. `WebUrl` shows
an S3 `AccessDenied` error until you upload the web client (next step).

### Try live updates

Open a WebSocket on a room with [wscat](https://github.com/websockets/wscat) (needs Node.js),
then post an idea from a second terminal:

```sh
npx wscat -c '<WebSocketUrl>?room_id=<room_id>'
curl -X POST -H 'X-User-Id: stu' -d '{"display_name": "Ann", "body": "Hi"}' \
  <ApiUrl>/rooms/<room_id>/ideas
```

An `idea_added` message shows up in wscat about half a second later. The message types are in
[docs/api.md](docs/api.md#messages). A newly deployed stack can take a few minutes before the
stream starts delivering anything.

If live updates stop, look at the function's logs and the failure queue:

```sh
sam logs --stack-name brainstorm-board -n StreamFunction --tail
aws sqs receive-message --queue-url <StreamFailuresQueueUrl>
```

A queue message only says which shard and sequence numbers failed, not the record itself.

### Upload the web client

```sh
python scripts/deploy_web.py --dry-run   # list what it would upload
python scripts/deploy_web.py
```

This reads the stack's outputs, uploads `web/` to the bucket and tells CloudFront to drop its
cached copy. It doesn't upload `web/config.js` as it is, since that points at your own computer.
It writes a new one with the stack's `ApiUrl` and `WebSocketUrl` instead. Files that aren't part
of the site (`node_modules/`, `package.json`, dotfiles) are skipped. Use `--stack` if you named
the stack something else.

Files are uploaded with `Cache-Control: max-age=0, s-maxage=86400`, so browsers check for a new
copy on every load and a deploy never leaves a phone running old and new modules together.
CloudFront keeps its own copy until the next deploy clears it.

Then open `<WebUrl>/#/host` on a laptop and `WebUrl` on your phone. It can take a few minutes
before CloudFront serves the new files.

### Add demo data

`seed.py` works against the deployed table too. Make sure `DYNAMODB_ENDPOINT_URL` isn't set,
otherwise it talks to DynamoDB Local:

```sh
unset DYNAMODB_ENDPOINT_URL
AWS_PROFILE=<your-profile> AWS_REGION=ca-central-1 python scripts/seed.py
```

### Show TTL deleting rooms

TTL removes a room some time after its `expires_at`, so seeing it takes two steps. `start`
makes a few rooms that expire in 5 minutes and saves their items to `benchmarks/results/`:

```sh
AWS_PROFILE=<your-profile> AWS_REGION=ca-central-1 python scripts/ttl_demo.py start
```

Then run `check` with the run id it printed, as often as you like. It records which items are
gone, reads the table's stream for their REMOVE records (each delete's time, and whether TTL made
it), and checks that the API already hides the rooms (`404`) before TTL deletes them. The stream
only keeps records for 24 hours, so check at least twice a day until everything is gone:

```sh
AWS_PROFILE=<your-profile> AWS_REGION=ca-central-1 python scripts/ttl_demo.py check <run id> --api-url <ApiUrl>
```

In our first run (`benchmarks/results/ttl-20261124T213237Z-*`) TTL deleted all 27 items 11 to 17
minutes after they expired. In the second (`ttl-20261127T011549Z-*`) all 27 items were gone 13 to
14 minutes after they expired, and each room's items went in the same second. The stream only
gave us the delete records for the 24 room items, not the 3 join-code items, so the delays in its
`deletes.csv` cover those 24; the `checks.csv` reads show the code items were gone too. AWS only
promises "within a few days", so these are two samples, not a guarantee.

DynamoDB Local (3.3.2) didn't delete anything in our test: the items were still there 27 minutes
after they expired. The script runs locally too (`DYNAMODB_ENDPOINT_URL=http://localhost:8000`),
and shows that reads hide expired rooms, but the actual deleting can only be seen on AWS.

### Run the benchmark on AWS

The same commands work against AWS. `run` makes its own on-demand table next to the deployed
one, so the demo table isn't touched, and deletes it at the end. `--provisioned` uses a table
with 20 write units instead (inside the free tier), to see throttling. `live` goes through the
deployed APIs (Streams, Lambda and API Gateway), using the `ApiUrl` and `WebSocketUrl` outputs:

```sh
unset DYNAMODB_ENDPOINT_URL
export AWS_PROFILE=<your-profile> AWS_REGION=ca-central-1
python scripts/benchmark.py run
python scripts/benchmark.py run --provisioned --scenarios hot-room --students 30,100
python scripts/benchmark.py live --api-url <ApiUrl> --ws-url <WebSocketUrl>
python scripts/benchmark.py cloudwatch <run id>   # a few minutes after a run
```

`cloudwatch` saves what DynamoDB itself counted during the run (throttled requests, transaction
conflicts, capacity used, server-side latency) to `bench-<run id>-cloudwatch.csv`. A full run
used about 140,000 write units on on-demand, roughly 10 cents. What we found is in
[docs/benchmark.md](docs/benchmark.md).

### Tear down

The bucket has to be empty before CloudFormation can delete it:

```sh
aws s3 rm s3://<WebBucketName> --recursive
sam delete
```

`sam delete` removes everything the template made, including the table and all its data.

## Group Members

| Name                   | Preferred Name | GitHub                                           |
| ---------------------- | -------------- | ------------------------------------------------ |
| Wei Ting Wang          | Annie          | [@AnnieWang331](https://github.com/AnnieWang331) |
| Myoungji Cho           | Roah           | [@Roahcho](https://github.com/Roahcho)           |
| Alexander King Perocho | Alex           | [@perochoa](https://github.com/perochoa)         |
| Sachin Singh           | Sachin         |                                                  |
| Muhammad Haadi Khawaja | Muhammad       | [@mkhawa5](https://github.com/mkhawa5)           |
