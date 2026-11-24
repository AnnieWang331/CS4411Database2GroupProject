"""The SAM template's table must match the one ``schema.py`` creates locally."""

from pathlib import Path

import yaml

from brainstorm import schema

TEMPLATE = Path(__file__).resolve().parents[2] / "template.yaml"


class _CfnLoader(yaml.SafeLoader):
    """SafeLoader that keeps CloudFormation tags (``!Ref``, ``!Sub``, ...) as plain values."""


def _any_tag(loader, _suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_CfnLoader.add_multi_constructor("!", _any_tag)


def _table() -> dict:
    template = yaml.load(TEMPLATE.read_text(), Loader=_CfnLoader)
    return template["Resources"]["Table"]["Properties"]


def test_table_matches_schema():
    props = _table()
    expected = schema.table_definition("unused")

    assert props["BillingMode"] == expected["BillingMode"]
    assert props["KeySchema"] == expected["KeySchema"]
    assert sorted(props["AttributeDefinitions"], key=str) == sorted(
        expected["AttributeDefinitions"], key=str
    )
    assert props["GlobalSecondaryIndexes"] == expected["GlobalSecondaryIndexes"]
    assert (
        props["StreamSpecification"]["StreamViewType"]
        == (expected["StreamSpecification"]["StreamViewType"])
    )


def test_table_ttl_and_encryption():
    props = _table()

    assert props["TimeToLiveSpecification"] == {
        "AttributeName": schema.TTL_ATTRIBUTE,
        "Enabled": True,
    }
    # Set explicitly so the report can cite it (AWS owned key).
    assert props["SSESpecification"] == {"SSEEnabled": False}
