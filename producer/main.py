import json
import os
import time

import requests
from kafka import KafkaProducer
from sseclient import SSEClient


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


WIKIMEDIA_STREAM_URL = os.getenv(
    "WIKIMEDIA_STREAM_URL",
    "https://stream.wikimedia.org/v2/stream/recentchange",
)
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "wikimedia.recentchange")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "broker:9092")
KAFKA_CLIENT_RETRY_MAX_ATTEMPTS = _env_int("KAFKA_CLIENT_RETRY_MAX_ATTEMPTS", 10)
KAFKA_CLIENT_RETRY_DELAY_SECONDS = _env_int("KAFKA_CLIENT_RETRY_DELAY_SECONDS", 5)


def create_producer():
    for _ in range(KAFKA_CLIENT_RETRY_MAX_ATTEMPTS):
        try:
            return KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
        except Exception:
            print("Kafka broker not available, retrying...")
            time.sleep(KAFKA_CLIENT_RETRY_DELAY_SECONDS)


def main():
    print("Starting Wikimedia Kafka Producer...")

    producer = create_producer()

    response = requests.get(WIKIMEDIA_STREAM_URL, stream=True)
    client = SSEClient(response)

    for event in client.events():
        if event.event == "message":
            try:
                data = json.loads(event.data)
                producer.send(KAFKA_TOPIC, value=data)
                print(f"Produced event to KAFKA: {data.get('title')}")
            except Exception as e:
                print(f"Error parsing event: {e}")


if __name__ == "__main__":
    main()
