import json
from types import SimpleNamespace

from document_id import opensearch_document_id


def _producer_wire_encode(value) -> bytes:
    """Same shape as producer KafkaProducer value_serializer."""
    return json.dumps(value).encode("utf-8")


def _consumer_wire_decode(raw: bytes):
    """Same shape as consumer KafkaConsumer value_deserializer."""
    return json.loads(raw.decode("utf-8"))


def test_kafka_value_round_trip_matches_apps():
    doc = {
        "id": 1,
        "meta": {"id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
        "title": "RoundTrip",
    }
    raw = _producer_wire_encode(doc)
    assert _consumer_wire_decode(raw) == doc


def test_kafka_value_round_trip_unicode_and_null_fields():
    doc = {"id": None, "title": "Évent 日本語", "comment": ""}
    assert _consumer_wire_decode(_producer_wire_encode(doc)) == doc


def test_opensearch_document_id_prefers_meta_uuid():
    doc = {"id": 999, "meta": {"id": "11111111-2222-3333-4444-555555555555"}}
    msg = SimpleNamespace(topic=None, partition=0, offset=1)
    assert (
        opensearch_document_id(doc, msg, kafka_topic_fallback="wikimedia.recentchange")
        == "11111111-2222-3333-4444-555555555555"
    )


def test_opensearch_document_id_skips_blank_meta_id():
    doc = {"id": 7, "meta": {"id": "   "}}
    msg = SimpleNamespace(topic=None, partition=0, offset=1)
    assert opensearch_document_id(doc, msg, kafka_topic_fallback="x") == "7"


def test_opensearch_document_id_uses_rcid_when_absent_meta_id():
    doc = {"id": 42}
    msg = SimpleNamespace(topic=None, partition=0, offset=1)
    assert opensearch_document_id(doc, msg, kafka_topic_fallback="x") == "42"


def test_opensearch_document_id_zero_rcid():
    doc = {"id": 0}
    msg = SimpleNamespace(topic=None, partition=0, offset=1)
    assert opensearch_document_id(doc, msg, kafka_topic_fallback="x") == "0"


def test_opensearch_document_id_kafka_fallback():
    doc = {}
    msg = SimpleNamespace(topic=None, partition=2, offset=99)
    assert (
        opensearch_document_id(doc, msg, kafka_topic_fallback="mytopic")
        == "kafka:mytopic:2:99"
    )


def test_opensearch_document_id_message_topic_wins():
    doc = {}
    msg = SimpleNamespace(topic="t1", partition=1, offset=3)
    assert (
        opensearch_document_id(doc, msg, kafka_topic_fallback="ignored")
        == "kafka:t1:1:3"
    )


def test_wikimedia_index_spec_has_expected_mapping_controls():
    from wikimedia_mappings import wikimedia_recentchange_index_spec

    spec = wikimedia_recentchange_index_spec()
    assert spec["mappings"]["dynamic"] is False
    props = spec["mappings"]["properties"]
    assert "title" in props
    assert "meta" in props
    assert props["meta"]["properties"]["dt"]["type"] == "date"
