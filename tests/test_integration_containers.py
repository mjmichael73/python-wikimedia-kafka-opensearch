import json
import uuid

import pytest

from tests.conftest import normalize_kafka_bootstrap


@pytest.mark.integration
def test_kafka_produce_consume_json_roundtrip(kafka_bootstrap):
    """Wire-format parity with producer/consumer serializers (Testcontainers Kafka)."""
    from kafka import KafkaConsumer, KafkaProducer

    topic = f"pwko-k-{uuid.uuid4().hex[:12]}"
    group = f"pwko-g-{uuid.uuid4().hex[:12]}"
    payload = {"id": 1001, "title": "KafkaIt", "meta": {"stream": "test"}}

    producer = KafkaProducer(
        bootstrap_servers=kafka_bootstrap,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    try:
        producer.send(topic, value=payload)
        producer.flush()
    finally:
        producer.close()

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=kafka_bootstrap,
        group_id=group,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=60_000,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )
    try:
        records = list(consumer)
    finally:
        consumer.close()

    assert len(records) == 1
    assert records[0].value == payload


@pytest.mark.integration
def test_kafka_to_opensearch_index_roundtrip(kafka_bootstrap, opensearch_host_port):
    """End-to-end: JSON in Kafka, consumer-style decode, index + get from OpenSearch."""
    from kafka import KafkaConsumer, KafkaProducer
    from opensearchpy import OpenSearch

    from main import opensearch_document_id
    from wikimedia_mappings import wikimedia_recentchange_create_index_body

    topic = f"pwko-kos-{uuid.uuid4().hex[:12]}"
    group = f"pwko-g2-{uuid.uuid4().hex[:12]}"
    index = f"pwko-it-{uuid.uuid4().hex[:10]}"
    payload = {
        "id": 4242,
        "title": "OpenSearchIntegration",
        "meta": {
            "id": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
            "dt": "2026-04-07T12:00:00Z",
        },
    }

    producer = KafkaProducer(
        bootstrap_servers=kafka_bootstrap,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    try:
        producer.send(topic, value=payload)
        producer.flush()
    finally:
        producer.close()

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=kafka_bootstrap,
        group_id=group,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=60_000,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )
    try:
        records = list(consumer)
    finally:
        consumer.close()

    assert len(records) == 1
    msg = records[0]
    assert msg.value == payload

    host, port = opensearch_host_port
    os_client = OpenSearch(
        hosts=[{"host": host, "port": port}],
        use_ssl=False,
        verify_certs=False,
        scheme="http",
    )
    try:
        os_client.indices.create(index=index, body=wikimedia_recentchange_create_index_body())
        doc_id = opensearch_document_id(msg.value, msg)
        os_client.index(index=index, id=doc_id, body=msg.value)
        os_client.indices.refresh(index=index)
        got = os_client.get(index=index, id=doc_id)
        assert got["found"] is True
        assert got["_source"]["title"] == "OpenSearchIntegration"
        assert got["_source"]["meta"]["id"] == payload["meta"]["id"]
    finally:
        if os_client.indices.exists(index=index):
            os_client.indices.delete(index=index)


@pytest.mark.integration
def test_normalize_kafka_bootstrap_strips_plaintext_prefix():
    assert normalize_kafka_bootstrap("PLAINTEXT://localhost:9092") == "localhost:9092"
    assert normalize_kafka_bootstrap("127.0.0.1:29092") == "127.0.0.1:29092"
