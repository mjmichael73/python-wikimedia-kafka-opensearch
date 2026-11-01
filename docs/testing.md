# Testing — Python Wikimedia Kafka OpenSearch

## Overview

Comprehensive testing strategy for a streaming pipeline with Python producer/consumer, Kafka, and OpenSearch.

## Test Strategy

| Test Type | Tools | Coverage Target |
|-----------|-------|-----------------|
| **Unit Tests** | pytest | 90% business logic |
| **Integration Tests** | Testcontainers | 85% pipeline |
| **E2E Tests** | Docker Compose | 80% end-to-end |
| **Load Tests** | Locust | Performance baselines |

## Setup

```bash
# Install test dependencies
pip install pytest pytest-asyncio testcontainers confluent-kafka

# Run tests
pytest

# Run with coverage
pytest --cov=producer --cov=consumer
```

## Unit Tests

### Producer Tests

```python
# producer/tests/test_producer.py
import pytest
from unittest.mock import Mock, patch
from producer import WikimediaProducer

class TestWikimediaProducer:
    def test_transform_event(self):
        producer = WikimediaProducer()
        
        event = {
            "id": 12345,
            "type": "edit",
            "namespace": 0,
            "title": "Python",
            "user": "testuser",
            "timestamp": "2024-01-01T00:00:00Z",
            "comment": "Test edit",
            "minor": False,
            "bot": False,
            "length": {"old": 100, "new": 150},
            "revision": {"old": "rev1", "new": "rev2"}
        }
        
        transformed = producer.transform_event(event)
        
        assert transformed["id"] == "12345"
        assert transformed["type"] == "edit"
        assert transformed["title"] == "Python"
    
    @patch('confluent_kafka.Producer')
    def test_publish_event(self, mock_producer):
        producer = WikimediaProducer()
        producer.producer = mock_producer
        
        event = {"id": "12345", "type": "edit"}
        producer.publish_event(event)
        
        mock_producer.produce.assert_called_once()
        mock_producer.flush.assert_called_once()
```

### Consumer Tests

```python
# consumer/tests/test_consumer.py
import pytest
from unittest.mock import Mock, patch
from consumer import OpenSearchConsumer

class TestOpenSearchConsumer:
    def test_transform_for_indexing(self):
        consumer = OpenSearchConsumer()
        
        message = {
            "id": "12345",
            "type": "edit",
            "title": "Python",
            "timestamp": "2024-01-01T00:00:00Z"
        }
        
        indexed = consumer.transform_for_indexing(message)
        
        assert indexed["_id"] == "12345"
        assert indexed["_index"] == "wikimedia-recentchanges"
    
    @patch('opensearchpy.OpenSearch')
    def test_index_document(self, mock_opensearch):
        consumer = OpenSearchConsumer()
        consumer.client = mock_opensearch
        
        doc = {"_id": "12345", "_index": "test", "data": {}}
        consumer.index_document(doc)
        
        mock_opensearch.index.assert_called_once()
```

## Integration Tests

```python
# tests/integration/test_pipeline.py
import pytest
from testcontainers.kafka import KafkaContainer
from testcontainers.opensearch import OpenSearchContainer

@pytest.fixture(scope="session")
def kafka():
    with KafkaContainer("confluentinc/cp-kafka:7.4.0") as kc:
        yield kc

@pytest.fixture(scope="session")
def opensearch():
    with OpenSearchContainer("opensearchproject/opensearch:2.17.0") as os:
        yield os

class TestPipelineIntegration:
    def test_end_to_end(self, kafka, opensearch):
        # Setup producer
        producer = WikimediaProducer(
            kafka_bootstrap=kafka.get_bootstrap_server()
        )
        
        # Setup consumer
        consumer = OpenSearchConsumer(
            kafka_bootstrap=kafka.get_bootstrap_server(),
            opensearch_url=opensearch.get_url()
        )
        
        # Produce test event
        event = {
            "id": "integration-test-1",
            "type": "edit",
            "title": "Integration Test",
            "timestamp": "2024-01-01T00:00:00Z"
        }
        producer.publish_event(event)
        
        # Consume and index
        consumer.consume_batch(timeout=10)
        
        # Verify in OpenSearch
        result = opensearch.client.search(
            index="wikimedia-recentchanges",
            body={"query": {"term": {"_id": "integration-test-1"}}}
        )
        
        assert result["hits"]["total"]["value"] == 1
```

## E2E Tests

```python
# tests/e2e/test_full_pipeline.py
import pytest
import time
import requests

class TestFullPipeline:
    def test_wikimedia_to_opensearch(self):
        # Wait for services to be ready
        time.sleep(10)
        
        # Check producer metrics
        producer_metrics = requests.get("http://localhost:8000/metrics")
        assert "messages_produced_total" in producer_metrics.text
        
        # Check consumer metrics
        consumer_metrics = requests.get("http://localhost:8001/metrics")
        assert "messages_consumed_total" in consumer_metrics.text
        
        # Check OpenSearch index
        opensearch_health = requests.get("http://localhost:9200/_cluster/health")
        assert opensearch_health.json()["status"] in ["green", "yellow"]
        
        # Check Grafana
        grafana_health = requests.get("http://localhost:3000/api/health")
        assert grafana_health.json()["database"] == "ok"
```

## Load Testing

```python
# tests/load/test_throughput.py
from locust import HttpUser, task, between

class WikimediaProducerUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def produce_event(self):
        event = {
            "id": f"load-test-{self.environment.runner.unique_count}",
            "type": "edit",
            "title": "Load Test",
            "timestamp": "2024-01-01T00:00:00Z"
        }
        
        self.client.post("/produce", json=event)
```

## Test Commands

```bash
# Run all tests
make test

# Run unit tests
make test-unit

# Run integration tests
make test-integration

# Run E2E tests
make test-e2e

# Run load tests
make test-load

# Run with coverage
make test-coverage
```

## Validation Checklist

- [ ] Unit tests for producer
- [ ] Unit tests for consumer
- [ ] Integration tests with Testcontainers
- [ ] E2E tests with Docker Compose
- [ ] Load tests for throughput
- [ ] Test coverage > 80%
- [ ] CI/CD pipeline configured
- [ ] Test data fixtures created
