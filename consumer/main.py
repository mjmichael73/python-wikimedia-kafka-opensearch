import json
import logging
import os
import time

from kafka import KafkaConsumer, KafkaProducer, TopicPartition
from kafka.structs import OffsetAndMetadata
from opensearchpy import OpenSearch

from document_id import opensearch_document_id as resolve_document_id
from observability import (
    configure_logging,
    consumer_dlq_total,
    consumer_indexed_total,
    consumer_offsets_committed_total,
    consumer_process_errors_total,
    start_observability_http,
)
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
OBS_HTTP_PORT = _env_int("OBS_HTTP_PORT", 8080)


def create_consumer(log: logging.Logger):
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
            log.warning(
                "Kafka broker not available, retrying",
                extra={"event": "kafka_connect_retry"},
            )
            time.sleep(KAFKA_CLIENT_RETRY_DELAY_SECONDS)


def create_dlq_producer(log: logging.Logger):
    for _ in range(KAFKA_CLIENT_RETRY_MAX_ATTEMPTS):
        try:
            return KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            )
        except Exception:
            log.warning(
                "Kafka broker not available for DLQ producer, retrying",
                extra={"event": "kafka_dlq_connect_retry"},
            )
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


def connect_opensearch(log: logging.Logger):
    for _ in range(OPENSEARCH_RETRY_MAX_ATTEMPTS):
        try:
            log.info("Connecting to OpenSearch", extra={"event": "opensearch_connect"})
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
                log.info(
                    "Created OpenSearch index with explicit mapping",
                    extra={"event": "index_created", "index": OPENSEARCH_INDEX},
                )

            return client

        except Exception as e:
            log.warning(
                "OpenSearch not available, retrying",
                extra={"event": "opensearch_retry", "error": str(e)},
            )
            time.sleep(OPENSEARCH_RETRY_DELAY_SECONDS)

    raise Exception("OpenSearch connection failed after multiple attempts.")


def opensearch_document_id(doc: dict, message) -> str:
    return resolve_document_id(doc, message, kafka_topic_fallback=KAFKA_TOPIC)


def main():
    log = configure_logging("consumer")
    ready = {"pipeline": False}
    start_observability_http(
        "consumer",
        OBS_HTTP_PORT,
        ready_fn=lambda: ready["pipeline"],
    )
    log.info(
        "Starting Kafka consumer",
        extra={"event": "startup", "obs_http_port": OBS_HTTP_PORT},
    )

    consumer = create_consumer(log)
    if consumer is None:
        log.error(
            "Kafka consumer could not be created",
            extra={"event": "kafka_unavailable"},
        )
        return
    os_client = connect_opensearch(log)
    dlq_producer = create_dlq_producer(log) if KAFKA_DLQ_TOPIC else None
    ready["pipeline"] = True
    if KAFKA_DLQ_TOPIC:
        log.info(
            "Dead-letter topic enabled",
            extra={"event": "dlq_config", "dlq_topic": KAFKA_DLQ_TOPIC},
        )
    else:
        log.info(
            "Dead-letter topic disabled; failed offsets still committed",
            extra={"event": "dlq_disabled"},
        )

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
            consumer_indexed_total.labels(index=OPENSEARCH_INDEX).inc()
            log.info(
                "Indexed document",
                extra={
                    "event": "indexed",
                    "doc_id": doc_id,
                    "index": OPENSEARCH_INDEX,
                    "kafka_offset": message.offset,
                },
            )
        except Exception as e:
            consumer_process_errors_total.labels(phase="index_or_validate").inc()
            log.exception(
                "Error processing message",
                extra={
                    "event": "process_error",
                    "kafka_offset": message.offset,
                },
            )
            if KAFKA_DLQ_TOPIC:
                if dlq_producer is None:
                    dlq_producer = create_dlq_producer(log)
                try:
                    publish_dlq(dlq_producer, message, doc, e)
                    consumer_dlq_total.labels(topic=KAFKA_DLQ_TOPIC).inc()
                    log.warning(
                        "Published message to DLQ",
                        extra={
                            "event": "dlq_publish",
                            "dlq_topic": KAFKA_DLQ_TOPIC,
                            "offset": message.offset,
                        },
                    )
                except Exception as dlq_err:
                    log.exception(
                        "DLQ publish failed; offset not committed",
                        extra={"event": "dlq_failed"},
                    )
                    continue
            else:
                log.warning(
                    "Skipping poison message without DLQ",
                    extra={"event": "skip_no_dlq"},
                )
        commit_current_offset(consumer, message)
        consumer_offsets_committed_total.labels(topic=message.topic).inc()


if __name__ == "__main__":
    main()
