import json
import os
import time

from kafka import KafkaConsumer, KafkaProducer, TopicPartition
from kafka.structs import OffsetAndMetadata
from opensearchpy import OpenSearch

from wikimedia_mappings import (
    WIKIMEDIA_INDEX_TEMPLATE_NAME,
    wikimedia_recentchange_create_index_body,
    wikimedia_recentchange_index_template_body,
)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "wikimedia.recentchange")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "broker:9092")
KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "wikimedia-consumer-group")
KAFKA_DLQ_TOPIC = os.getenv("KAFKA_DLQ_TOPIC", "wikimedia.recentchange.dlq").strip()
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "opensearch-node1")
OPENSEARCH_PORT = _env_int("OPENSEARCH_PORT", 9200)
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "wikimedia-changes")
KAFKA_CLIENT_RETRY_MAX_ATTEMPTS = _env_int("KAFKA_CLIENT_RETRY_MAX_ATTEMPTS", 10)
KAFKA_CLIENT_RETRY_DELAY_SECONDS = _env_int("KAFKA_CLIENT_RETRY_DELAY_SECONDS", 5)
OPENSEARCH_RETRY_MAX_ATTEMPTS = _env_int("OPENSEARCH_RETRY_MAX_ATTEMPTS", 20)
OPENSEARCH_RETRY_DELAY_SECONDS = _env_int("OPENSEARCH_RETRY_DELAY_SECONDS", 5)


def create_consumer():
    for _ in range(KAFKA_CLIENT_RETRY_MAX_ATTEMPTS):
        try:
            return KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="latest",
                group_id=KAFKA_CONSUMER_GROUP,
                enable_auto_commit=False,
            )
        except Exception:
            print("Kafka broker not available, retrying...")
            time.sleep(KAFKA_CLIENT_RETRY_DELAY_SECONDS)


def create_dlq_producer():
    for _ in range(KAFKA_CLIENT_RETRY_MAX_ATTEMPTS):
        try:
            return KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            )
        except Exception:
            print("Kafka broker not available for DLQ producer, retrying...")
            time.sleep(KAFKA_CLIENT_RETRY_DELAY_SECONDS)
    raise RuntimeError("Kafka DLQ producer connection failed after multiple attempts.")


def commit_current_offset(consumer, message) -> None:
    tp = TopicPartition(message.topic, message.partition)
    meta = OffsetAndMetadata(
        message.offset + 1,
        "",
        getattr(message, "leader_epoch", -1),
    )
    consumer.commit(offsets={tp: meta})


def publish_dlq(dlq_producer, message, doc, error: Exception) -> None:
    key = message.key
    envelope = {
        "error": str(error),
        "error_type": type(error).__name__,
        "source_topic": message.topic,
        "partition": message.partition,
        "offset": message.offset,
        "timestamp": message.timestamp,
        "key": (key.decode("utf-8", errors="replace") if isinstance(key, (bytes, bytearray)) else key),
        "document": doc,
    }
    dlq_producer.send(KAFKA_DLQ_TOPIC, value=envelope)
    dlq_producer.flush(timeout=30)


def connect_opensearch():
    for _ in range(OPENSEARCH_RETRY_MAX_ATTEMPTS):
        try:
            print("Trying to connect to OpenSearch...")
            client = OpenSearch(
                hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
                use_ssl=False,
                verify_certs=False,
                scheme="http",
            )
            client.indices.put_index_template(
                name=WIKIMEDIA_INDEX_TEMPLATE_NAME,
                body=wikimedia_recentchange_index_template_body(),
            )
            if not client.indices.exists(index=OPENSEARCH_INDEX):
                client.indices.create(
                    index=OPENSEARCH_INDEX,
                    body=wikimedia_recentchange_create_index_body(),
                )
                print(f"Index {OPENSEARCH_INDEX} created with explicit mapping.")

            return client

        except Exception as e:
            print(f"OpenSearch not available, retrying... {e}")
            time.sleep(OPENSEARCH_RETRY_DELAY_SECONDS)

    raise Exception("OpenSearch connection failed after multiple attempts.")


def opensearch_document_id(doc: dict, message) -> str:
    """
    Choose a stable OpenSearch _id: WMF meta.id (event UUID), else recentchange id
    (rcid), else Kafka topic/partition/offset so every consumed record is indexable.
    """
    meta = doc.get("meta")
    if isinstance(meta, dict):
        mid = meta.get("id")
        if mid is not None and str(mid).strip() != "":
            return str(mid)
    rid = doc.get("id")
    if rid is not None:
        return str(rid)
    topic = getattr(message, "topic", None) or KAFKA_TOPIC
    partition = message.partition
    offset = message.offset
    return f"kafka:{topic}:{partition}:{offset}"


def main():
    print("Starting Kafka Consumer...")

    consumer = create_consumer()
    os_client = connect_opensearch()
    dlq_producer = create_dlq_producer() if KAFKA_DLQ_TOPIC else None
    if KAFKA_DLQ_TOPIC:
        print(f"Dead-letter topic: {KAFKA_DLQ_TOPIC} (manual offset commit after each message).")
    else:
        print("Dead-letter topic disabled; failed messages will be skipped after commit.")

    for message in consumer:
        doc = message.value
        try:
            if not isinstance(doc, dict):
                raise TypeError(
                    f"Expected dict document, got {type(doc).__name__}",
                )
            doc_id = opensearch_document_id(doc, message)
            os_client.index(
                index=OPENSEARCH_INDEX,
                id=doc_id,
                body=doc,
            )
            print(f"Indexed document with ID: {doc_id}")
        except Exception as e:
            print(f"Error processing message: {e}")
            if KAFKA_DLQ_TOPIC:
                if dlq_producer is None:
                    dlq_producer = create_dlq_producer()
                try:
                    publish_dlq(dlq_producer, message, doc, e)
                    print(f"Sent message to DLQ topic {KAFKA_DLQ_TOPIC} (offset {message.offset}).")
                except Exception as dlq_err:
                    print(
                        f"DLQ publish failed, offset not committed (will retry): {dlq_err}",
                    )
                    continue
            else:
                print("Committing offset to skip poison message (no DLQ).")
        commit_current_offset(consumer, message)


if __name__ == "__main__":
    main()
