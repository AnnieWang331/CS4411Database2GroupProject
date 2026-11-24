"""The SAM template: its table must match ``schema.py``, its handlers must exist in ``src/``."""

import importlib
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


def _resources() -> dict:
    return yaml.load(TEMPLATE.read_text(), Loader=_CfnLoader)["Resources"]


def _table() -> dict:
    return _resources()["Table"]["Properties"]


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


def test_function_handlers_exist():
    functions = {
        name: r["Properties"]["Handler"]
        for name, r in _resources().items()
        if r["Type"] == "AWS::Serverless::Function"
    }

    assert set(functions) == {"ApiFunction", "WebSocketFunction", "StreamFunction"}
    for handler in functions.values():
        module, func = handler.rsplit(".", 1)
        assert callable(getattr(importlib.import_module(module), func))


def test_stream_mapping_cant_be_blocked_by_one_record():
    stream = _resources()["StreamMapping"]["Properties"]

    # broadcast.lambda_handler returns batchItemFailures, which only works with this on.
    assert stream["FunctionResponseTypes"] == ["ReportBatchItemFailures"]
    assert stream["BisectBatchOnFunctionError"] is True
    assert stream["MaximumRetryAttempts"] > 0
    assert stream["DestinationConfig"]["OnFailure"]["Destination"] == "StreamFailures.Arn"
