"""Shared fixtures: a fresh brainstorm table on DynamoDB Local for every test."""

import os
import uuid
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from brainstorm import db, schema

LOCAL_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT_URL", "http://localhost:8000")


def _local_is_up() -> bool:
    try:
        urlopen(LOCAL_ENDPOINT, timeout=1)
    except URLError as err:
        # DynamoDB Local answers a bare GET with HTTP 400; only a refused connection means down.
        return hasattr(err, "code")
    return True


@pytest.fixture(scope="session")
def dynamodb():
    """DynamoDB Local service resource; skips the test run if DynamoDB Local isn't running."""
    if not _local_is_up():
        pytest.skip(f"DynamoDB Local is not running at {LOCAL_ENDPOINT} (see README)")
    return db.resource(LOCAL_ENDPOINT)


@pytest.fixture
def table(dynamodb):
    """A newly created, uniquely named table that is deleted after the test."""
    name = f"test-{uuid.uuid4().hex[:12]}"
    created = schema.create_table(dynamodb, name)
    yield created
    created.delete()
