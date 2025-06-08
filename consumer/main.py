import json
import time
from kafka import KafkaConsumer
from opensearchpy import OpenSearch

KAFKA_TOPIC = "wikimedia.recentchange"
KAFKA_BROKERS = "broker:9092"
OPENSEARCH_HOST = "opensearch-node1"
OPENSEARCH_INDEX = "wikimedia-changes"


def create_consumer():
    for _ in range(10):
        try:
            return KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BROKERS,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="latest",
                group_id="wikimedia-consumer-group",
            )
        except Exception:
            print("Kafka broker not available, retrying...")
            time.sleep(5)


def connect_opensearch():
    for _ in range(20):
        try:
            print("Trying to connect to OpenSearch...")
            client = OpenSearch(
                hosts=[{"host": OPENSEARCH_HOST, "port": 9200}],
                use_ssl=False,
                verify_certs=False,
                scheme="http",
            )
            if not client.indices.exists(index=OPENSEARCH_INDEX):
                client.indices.create(index=OPENSEARCH_INDEX)
                print(f"Index {OPENSEARCH_INDEX} created.")

            return client

        except Exception as e:
            print(f"OpenSearch not available, retrying... {e}")
            time.sleep(5)

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
