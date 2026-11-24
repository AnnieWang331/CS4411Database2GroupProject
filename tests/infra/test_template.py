"""The SAM template: its table must match ``schema.py``, its handlers must exist in ``src/``."""

import importlib.util
import json
from pathlib import Path

import yaml

from brainstorm import schema

TEMPLATE = Path(__file__).resolve().parents[2] / "template.yaml"
SAMPLES = Path(__file__).resolve().parents[1] / "brainstorm" / "test_stream_events.py"


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


def test_stream_filter_only_drops_items_that_never_become_messages():
    # Reuse the sample items and record builder from the stream event tests.
    spec = importlib.util.spec_from_file_location("samples", SAMPLES)
    samples = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(samples)

    filters = _resources()["StreamMapping"]["Properties"]["FilterCriteria"]["Filters"]
    patterns = [json.loads(f["Pattern"]) for f in filters]
    by_image = {
        "NewImage": patterns[0]["dynamodb"]["NewImage"],
        "OldImage": patterns[1]["dynamodb"]["OldImage"],
    }
    dropped = [set(p["entity_type"]["S"][0]["anything-but"]) for p in by_image.values()]
    assert dropped[0] == dropped[1]
    assert patterns[1]["eventName"] == ["REMOVE"]

    items = {
        "CONNECTION": samples.connection(),
        "CONNECTION_LOOKUP": samples.connection_lookup(),
        "VOTE": samples.vote(),
        "ROOM_CODE": samples.code(),
    }
    assert set(items) == dropped[0]
    for entity, item in items.items():
        assert item["entity_type"] == entity
        for name, new, old in [
            ("INSERT", item, None),
            ("MODIFY", item, item),
            ("REMOVE", None, item),
        ]:
            rec = samples.record(name, new=new, old=old, identity=samples.TTL_IDENTITY)
            assert samples.to_event(rec) is None, (entity, name)
