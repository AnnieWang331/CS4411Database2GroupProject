"""Tests for the table definition."""

from brainstorm import schema

FREE_TIER_UNITS = 25


def test_on_demand_by_default():
    definition = schema.table_definition("t")
    assert definition["BillingMode"] == "PAY_PER_REQUEST"
    assert "ProvisionedThroughput" not in definition["GlobalSecondaryIndexes"][0]


def test_provisioned_capacity_fits_always_free_tier():
    definition = schema.table_definition("t", provisioned=True)
    gsi = definition["GlobalSecondaryIndexes"][0]["ProvisionedThroughput"]
    for unit in ("ReadCapacityUnits", "WriteCapacityUnits"):
        total = definition["ProvisionedThroughput"][unit] + gsi[unit]
        assert total <= FREE_TIER_UNITS
