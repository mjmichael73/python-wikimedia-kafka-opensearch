import json
import requests
from sseclient import SSEClient
from kafka import KafkaProducer
import time

WIKIMEDIA_STREAM_URL = "https://stream.wikimedia.org/v2/stream/recentchange"
KAFKA_TOPIC = "wikimedia.recentchange"
KAFKA_BROKERS = ["broker:9092"]


def create_producer():
    for _ in range(10):
        try:
            return KafkaProducer(
                bootstrap_servers=KAFKA_BROKERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
        except Exception:
            print("Kafka broker not available, retrying...")
            time.sleep(5)


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
