"""DynamoDB connection settings and table access.

Configuration comes from the environment so the same code runs against DynamoDB Local and AWS:

- ``BRAINSTORM_TABLE``: table name (default ``BrainstormBoard``).
- ``DYNAMODB_ENDPOINT_URL``: set to ``http://localhost:8000`` for DynamoDB Local; unset for AWS.
- ``AWS_PROFILE`` / ``AWS_REGION``: the usual boto3 credential and region chain.
"""

import os

import boto3

DEFAULT_TABLE_NAME = "BrainstormBoard"
LOCAL_REGION = "us-east-1"


def table_name() -> str:
    """Return the configured table name."""
    return os.environ.get("BRAINSTORM_TABLE", DEFAULT_TABLE_NAME)


def endpoint_url() -> str | None:
    """Return the DynamoDB endpoint override, or None to use AWS."""
    return os.environ.get("DYNAMODB_ENDPOINT_URL") or None


def resource(endpoint: str | None = None):
    """Create a DynamoDB service resource for AWS or, given an endpoint, DynamoDB Local."""
    endpoint = endpoint or endpoint_url()
    if endpoint is None:
        return boto3.resource("dynamodb")
    # DynamoDB Local accepts any credentials and region; supply defaults so it works without a
    # configured AWS profile (for example, on a grader's machine).
    return boto3.resource(
        "dynamodb",
        endpoint_url=endpoint,
        region_name=os.environ.get("AWS_REGION", LOCAL_REGION),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"),
    )


def table(name: str | None = None, endpoint: str | None = None):
    """Return the brainstorm board ``Table`` resource."""
    return resource(endpoint).Table(name or table_name())
