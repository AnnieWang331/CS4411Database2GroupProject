"""TransactWriteItems with retries on transaction conflicts (docs/data-model.md, section 4).

Condition builders (``Attr``) can't be used inside ``TransactItems``: boto3 would hoist the
placeholders to the top level of the request, which ``TransactWriteItems`` rejects. Transactions
therefore use expression strings; values are still plain Python types because the client comes
from the ``Table`` resource and marshals them.
"""

import random
import time
import uuid
from typing import Any

from botocore.exceptions import ClientError

MAX_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 0.05
# Cancellation reasons worth retrying: a concurrent transaction on the same item, or throttling
# (ProvisionedThroughputExceeded on provisioned tables, ThrottlingError while on-demand scales).
RETRYABLE_CODES = {"TransactionConflict", "ProvisionedThroughputExceeded", "ThrottlingError"}


class TransactionCanceledError(Exception):
    """A transaction was cancelled; ``codes`` lists one reason code per action, in order."""

    def __init__(self, codes: list[str]) -> None:
        super().__init__(f"transaction cancelled: {codes}")
        self.codes = codes

    def failed(self, index: int) -> bool:
        """Return True if the action at ``index`` failed its condition."""
        return self.codes[index] == "ConditionalCheckFailed"


def transact_write(table, items: list[dict[str, Any]], token: str | None = None) -> None:
    """Run ``TransactWriteItems`` on ``table``, retrying conflicts and throttling with backoff.

    Each item is ``{"Put"|"Update"|"Delete"|"ConditionCheck": {...}}`` without ``TableName``;
    the table name is filled in. Retries reuse one ``ClientRequestToken`` so they are idempotent.

    Raises:
        TransactionCanceledError: A condition failed, or conflicts or throttling persisted
            after ``MAX_ATTEMPTS`` attempts.
    """
    for item in items:
        for action in item.values():
            action["TableName"] = table.name
    token = token or uuid.uuid4().hex

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            table.meta.client.transact_write_items(TransactItems=items, ClientRequestToken=token)
            return
        except ClientError as err:
            if err.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            codes = [r.get("Code", "None") for r in err.response.get("CancellationReasons", [])]
            failures = {code for code in codes if code != "None"}
            # Retrying can't fix a failed condition, so only retry if every failure is retryable.
            if not failures or not failures <= RETRYABLE_CODES or attempt == MAX_ATTEMPTS:
                raise TransactionCanceledError(codes) from err
            # The SDK doesn't retry cancelled transactions, so back off with full jitter
            # (up to 0.1, 0.2, 0.4, 0.8 s between the five attempts).
            time.sleep(random.uniform(0, BASE_BACKOFF_SECONDS * 2**attempt))
