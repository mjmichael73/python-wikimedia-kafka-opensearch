import json
import os
import time

import requests
from kafka import KafkaProducer
from sseclient import SSEClient

from observability import (
    configure_logging,
    producer_errors_total,
    producer_events_total,
    start_observability_http,
)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


WIKIMEDIA_STREAM_URL = os.getenv(
    "WIKIMEDIA_STREAM_URL",
    "https://stream.wikimedia.org/v2/stream/recentchange",
)
# Wikimedia blocks generic defaults like python-requests/*. Set your URL/email via env if needed.
_DEFAULT_WIKIMEDIA_UA = (
    "python-wikimedia-kafka-opensearch/1.0 "
    "(+https://meta.wikimedia.org/wiki/User-Agent_policy; Docker demo producer)"
)
_raw_wikimedia_ua = os.getenv("WIKIMEDIA_HTTP_USER_AGENT", "").strip()
WIKIMEDIA_HTTP_USER_AGENT = _raw_wikimedia_ua or _DEFAULT_WIKIMEDIA_UA
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "wikimedia.recentchange")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "broker:9092")
KAFKA_CLIENT_RETRY_MAX_ATTEMPTS = _env_int("KAFKA_CLIENT_RETRY_MAX_ATTEMPTS", 10)
KAFKA_CLIENT_RETRY_DELAY_SECONDS = _env_int("KAFKA_CLIENT_RETRY_DELAY_SECONDS", 5)
OBS_HTTP_PORT = _env_int("OBS_HTTP_PORT", 8080)


def create_producer(log):
    for _ in range(KAFKA_CLIENT_RETRY_MAX_ATTEMPTS):
        try:
            return KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
        except Exception:
            log.warning(
                "Kafka broker not available, retrying",
                extra={"event": "kafka_connect_retry"},
            )
            producer_errors_total.labels(phase="kafka_connect").inc()
            time.sleep(KAFKA_CLIENT_RETRY_DELAY_SECONDS)


def main():
    log = configure_logging("producer")
    ready = {"kafka": False}
    start_observability_http(
        "producer",
        OBS_HTTP_PORT,
        ready_fn=lambda: ready["kafka"],
    )
    log.info(
        "Starting Wikimedia Kafka Producer",
        extra={"event": "startup", "obs_http_port": OBS_HTTP_PORT},
    )

    producer = create_producer(log)
    ready["kafka"] = producer is not None
    if producer is None:
        log.error(
            "Kafka producer could not be created",
            extra={"event": "kafka_unavailable"},
        )
        return

    reconnect_delay = _env_int("WIKIMEDIA_SSE_RECONNECT_DELAY_SECONDS", 5)

    while True:
        try:
            log.info(
                "Connecting to Wikimedia SSE stream",
                extra={"event": "sse_connect", "url": WIKIMEDIA_STREAM_URL},
            )
            # Connect timeout only; read None avoids closing an idle SSE from the client side.
            with requests.get(
                WIKIMEDIA_STREAM_URL,
                stream=True,
                timeout=(30, None),
                headers={
                    "Accept": "text/event-stream",
                    "User-Agent": WIKIMEDIA_HTTP_USER_AGENT,
                },
            ) as response:
                response.raise_for_status()
                client = SSEClient(response)
                for event in client.events():
                    if event.event == "message":
                        try:
                            data = json.loads(event.data)
                            producer.send(KAFKA_TOPIC, value=data)
                            producer_events_total.labels(topic=KAFKA_TOPIC).inc()
                            log.info(
                                "Produced event to Kafka",
                                extra={
                                    "event": "produced",
                                    "topic": KAFKA_TOPIC,
                                    "title": data.get("title"),
                                },
                            )
                        except Exception:
                            producer_errors_total.labels(phase="parse_or_send").inc()
                            log.exception(
                                "Error parsing or sending SSE event",
                                extra={"event": "producer_error", "phase": "parse_or_send"},
                            )
            log.info(
                "SSE stream closed, reconnecting",
                extra={"event": "sse_disconnected"},
            )
        except requests.RequestException as e:
            log.warning(
                "SSE connection failed, reconnecting",
                extra={"event": "sse_reconnect", "error": str(e)},
            )
            producer_errors_total.labels(phase="sse_connect").inc()
        except Exception:
            producer_errors_total.labels(phase="sse_stream").inc()
            log.exception(
                "Unexpected error in SSE loop, reconnecting",
                extra={"event": "sse_unexpected"},
            )

        time.sleep(reconnect_delay)


if __name__ == "__main__":
    main()
