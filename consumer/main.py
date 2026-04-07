import json
import os
import time

from kafka import KafkaConsumer
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
            )
        except Exception:
            print("Kafka broker not available, retrying...")
            time.sleep(KAFKA_CLIENT_RETRY_DELAY_SECONDS)


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


def main():
    print("Starting Kafka Consumer...")

    consumer = create_consumer()
    os_client = connect_opensearch()

    for message in consumer:
        try:
            doc = message.value
            doc_id = doc.get("id")
            os_client.index(
                index=OPENSEARCH_INDEX,
                id=doc_id,
                body=doc,
            )
            print(f"Indexed document with ID: {doc_id}")
        except Exception as e:
            print(f"Error indexing document: {e}")
            continue


if __name__ == "__main__":
    main()
