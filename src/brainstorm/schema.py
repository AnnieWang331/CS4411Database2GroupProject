"""Table definition for the brainstorm board (see docs/data-model.md, section 3)."""

from typing import Any

GSI1 = "GSI1"
TTL_ATTRIBUTE = "expires_at"

# Room META attributes copied into GSI1 so "my rooms" needs no extra reads.
GSI1_PROJECTED = [
    "room_id",
    "code",
    "topic",
    "status",
    "created_at",
    "closed_at",
    "expires_at",
    "entity_type",
]

# Provisioned capacity that together stays within the always-free 25 RCU / 25 WCU. The table gets
# most of it because a vote is a 3-item transaction costing about 6 WCU (each item is prepared and
# committed); GSI1 is only written when a room is created or closed.
TABLE_UNITS = 20
GSI1_UNITS = 5


def table_definition(name: str, provisioned: bool = False) -> dict[str, Any]:
    """Return the ``CreateTable`` arguments for the brainstorm table.

    Args:
        name: Table name.
        provisioned: Use small provisioned capacity instead of on-demand billing.
    """
    gsi1: dict[str, Any] = {
        "IndexName": GSI1,
        "KeySchema": [
            {"AttributeName": "GSI1PK", "KeyType": "HASH"},
            {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "INCLUDE", "NonKeyAttributes": GSI1_PROJECTED},
    }
    definition: dict[str, Any] = {
        "TableName": name,
        "KeySchema": [
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": attr, "AttributeType": "S"}
            for attr in ("PK", "SK", "GSI1PK", "GSI1SK")
        ],
        "GlobalSecondaryIndexes": [gsi1],
        "StreamSpecification": {"StreamEnabled": True, "StreamViewType": "NEW_AND_OLD_IMAGES"},
    }
    if provisioned:
        definition["BillingMode"] = "PROVISIONED"
        definition["ProvisionedThroughput"] = {
            "ReadCapacityUnits": TABLE_UNITS,
            "WriteCapacityUnits": TABLE_UNITS,
        }
        gsi1["ProvisionedThroughput"] = {
            "ReadCapacityUnits": GSI1_UNITS,
            "WriteCapacityUnits": GSI1_UNITS,
        }
    else:
        definition["BillingMode"] = "PAY_PER_REQUEST"
    return definition


def create_table(dynamodb, name: str, provisioned: bool = False):
    """Create the table, wait until it is active, enable TTL, and return the ``Table``."""
    table = dynamodb.create_table(**table_definition(name, provisioned))
    table.wait_until_exists()
    dynamodb.meta.client.update_time_to_live(
        TableName=name,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": TTL_ATTRIBUTE},
    )
    return table
