# CS4411Database2GroupProject

## Classroom Brainstorm Board in Real-Time using Amazon DynamoDB

Group project for **COMPSCI 4411/9538 (Databases II)** at Western University, Fall 2026, in the
_In-Depth Analysis of Data Management Systems_ category (Amazon DynamoDB, Group 20).

### Overview

Relational databases can struggle when an application needs to manage large amounts of rapidly
changing data at scale. Amazon DynamoDB is a fully managed, serverless NoSQL key-value database
built for this problem. It offers automatic scaling, high availability, and low-latency access
for predictable access patterns.

To demonstrate DynamoDB, we are building a **live, collaborative brainstorm board**:

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
- Final report (LaTeX/Overleaf template)
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
- Docker or Podman (we use it to run DynamoDB Local)

### 1. Install the Python packages

Make a virtual environment and turn it on. For example, run `python -m venv .venv` and then
`source .venv/bin/activate` (a pyenv virtualenv works too). Then install the packages:

```sh
pip install -r requirements-dev.txt
```

This installs boto3 (the AWS library for Python) plus pytest and ruff, which we use for testing
and linting.

### 2. Start DynamoDB Local

```sh
docker run -d --rm --name dynamodb-local -p 8000:8000 amazon/dynamodb-local \
  -jar DynamoDBLocal.jar -inMemory -sharedDb
```

If you use Podman, change `docker` to `podman` and use `docker.io/amazon/dynamodb-local` as the
image name. Because of `-inMemory`, all the data disappears when the container stops, which is
handy for testing. To stop it, run `docker stop dynamodb-local`.

### 3. Create the table and add demo data

```sh
export DYNAMODB_ENDPOINT_URL=http://localhost:8000
python scripts/create_table.py
python scripts/seed.py
```

The first line points our scripts at DynamoDB Local instead of AWS.

`create_table.py` creates our `BrainstormBoard` table. It also sets up a secondary index (GSI1)
for listing an instructor's rooms, turns on DynamoDB Streams (which we'll use for live updates),
and turns on Time to Live (TTL) so old rooms delete themselves. If you want to start over, add
`--recreate` to delete the local table and make it again.

By default the table uses on-demand billing, where AWS charges per request. If you add
`--provisioned`, it reserves 20 read and 20 write units for the table and 5 of each for the index
instead. That stays inside the 25 units AWS gives you for free.

`seed.py` makes a demo room with a few students, ideas, votes and comments, and prints the board
so you can see it worked.

### 4. Run the tests

```sh
pytest
```

The tests make their own tables in DynamoDB Local and delete them afterwards. If DynamoDB Local
isn't running, the tests that need it are skipped instead of failing.

Lint: run `ruff format --check .` and `ruff check .` before you push. The settings (like our
100-character line length) are in `pyproject.toml`.

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

### Settings

Our code reads these environment variables:

- `DYNAMODB_ENDPOINT_URL`: where DynamoDB is. Set it to `http://localhost:8000` for DynamoDB
  Local. Leave it unset to use real AWS.
- `BRAINSTORM_TABLE`: the table name. The default is `BrainstormBoard`.
- `CORS_ALLOW_ORIGIN`: which website is allowed to call the API from a browser. The default is
  `*` (any site).
- `AWS_PROFILE` and `AWS_REGION`: which AWS account and region to use. These only matter when
  you're using real AWS.

To check that your AWS profile can reach DynamoDB, run `python scripts/check_aws.py`.

### Where things are

```text
docs/data-model.md     How we store the data in DynamoDB, and why
docs/api.md            The HTTP API: routes, errors and who can call what
docs/project-info/     Course requirements: project outline, grading rubric and our proposal
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
scripts/               Scripts to create the table, add demo data, run the API locally and
                       check AWS access
tests/                 Our tests (they run against DynamoDB Local)
```

### Resources

- [DynamoDB User Guide](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html)
- [Working with DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithDynamo.html)

## Group Members

| Name                   | Preferred Name | GitHub                                           |
| ---------------------- | -------------- | ------------------------------------------------ |
| Wei Ting Wang          | Annie          | [@AnnieWang331](https://github.com/AnnieWang331) |
| Myoungji Cho           | Roah           | [@Roahcho](https://github.com/Roahcho)           |
| Alexander King Perocho | Alex           | [@perochoa](https://github.com/perochoa)         |
| Sachin Singh           | Sachin         |                                                  |
| Muhammad Haadi Khawaja | Muhammad       | [@mkhawa5](https://github.com/mkhawa5)           |

Our Group Excel Sheet: \
<https://docs.google.com/spreadsheets/d/1D12NDc1bbNykrmjbw6rxI_1_SfABOOpvLZ4hAwmwTV8/edit?pli=1&gid=0#gid=0>
