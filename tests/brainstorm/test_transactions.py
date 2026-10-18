"""Tests for transaction retries, using a stub client (DynamoDB Local never throttles)."""

from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from brainstorm import transactions
from brainstorm.transactions import TransactionCanceledError, transact_write


def cancelled(*codes: str) -> ClientError:
    """Build the error DynamoDB returns for a cancelled transaction."""
    response = {
        "Error": {"Code": "TransactionCanceledException", "Message": "cancelled"},
        "CancellationReasons": [{"Code": code} for code in codes],
    }
    return ClientError(response, "TransactWriteItems")


class StubTable:
    """A table whose client raises the given errors in turn, then succeeds."""

    name = "stub"

    def __init__(self, *errors: ClientError) -> None:
        self.errors = list(errors)
        self.tokens: list[str] = []
        self.meta = SimpleNamespace(client=SimpleNamespace(transact_write_items=self._call))

    def _call(self, TransactItems, ClientRequestToken):  # noqa: N803 - boto3 parameter names
        self.tokens.append(ClientRequestToken)
        if self.errors:
            raise self.errors.pop(0)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(transactions.time, "sleep", lambda _: None)


def items() -> list[dict]:
    return [{"ConditionCheck": {"Key": {"PK": "a", "SK": "b"}, "ConditionExpression": "x"}}]


@pytest.mark.parametrize(
    "code", ["TransactionConflict", "ProvisionedThroughputExceeded", "ThrottlingError"]
)
def test_retries_retryable_codes_with_same_token(code):
    table = StubTable(cancelled("None", code), cancelled(code, "None"))
    transact_write(table, items())
    assert len(table.tokens) == 3
    assert len(set(table.tokens)) == 1


def test_does_not_retry_failed_condition():
    table = StubTable(cancelled("ConditionalCheckFailed", "None"))
    with pytest.raises(TransactionCanceledError) as exc:
        transact_write(table, items())
    assert exc.value.failed(0)
    assert len(table.tokens) == 1


def test_does_not_retry_condition_failure_mixed_with_throttling():
    table = StubTable(cancelled("ConditionalCheckFailed", "ThrottlingError"))
    with pytest.raises(TransactionCanceledError):
        transact_write(table, items())
    assert len(table.tokens) == 1


def test_gives_up_after_max_attempts():
    table = StubTable(*[cancelled("ThrottlingError")] * transactions.MAX_ATTEMPTS)
    with pytest.raises(TransactionCanceledError) as exc:
        transact_write(table, items())
    assert exc.value.codes == ["ThrottlingError"]
    assert len(table.tokens) == transactions.MAX_ATTEMPTS


def test_other_client_errors_propagate():
    error = ClientError({"Error": {"Code": "ValidationException"}}, "TransactWriteItems")
    with pytest.raises(ClientError):
        transact_write(StubTable(error), items())
