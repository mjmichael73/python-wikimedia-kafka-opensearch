# Architecture — Python Wikimedia Kafka OpenSearch

## Overview

An end-to-end streaming demo: Python producer reads Wikimedia recent change SSE stream, publishes to Kafka, consumer indexes into OpenSearch. Includes Prometheus + Grafana monitoring.

**Stack:** Python 3.11, Kafka (KRaft), OpenSearch 2.17, Prometheus, Grafana, Docker Compose

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Wikimedia SSE Stream                                │
│                    (https://stream.wikimedia.org)                           │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Python Producer                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │ SSE Client  │  │  Transformer│  │  Kafka      │                         │
│  │ (httpx)     │  │  (JSON)     │  │  Producer   │                         │
│  └─────────────┘  └─────────────┘  └─────────────┘                         │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Prometheus Metrics                               │    │
│  │  • messages_produced_total                                         │    │
│  │  • produce_latency_seconds                                         │    │
│  │  • sse_reconnects_total                                            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Apache Kafka                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Topic: wikimedia.recentchanges                   │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │    │
│  │  │  Partition 0│  │  Partition 1│  │  Partition 2│                 │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Dead Letter Queue (DLQ)                          │    │
│  │                    Topic: wikimedia.dlq                             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Python Consumer                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │  Kafka      │  │  Transformer│  │  OpenSearch │                         │
│  │  Consumer   │  │  (Index)    │  │  Client     │                         │
│  └─────────────┘  └─────────────┘  └─────────────┘                         │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Prometheus Metrics                               │    │
│  │  • messages_consumed_total                                         │    │
│  │  • consume_latency_seconds                                         │    │
│  │  • indexing_errors_total                                           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           OpenSearch 2.17                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Index: wikimedia-recentchanges                   │    │
│  │  • idempotent indexing (by revision ID)                            │    │
│  │  • full-text search                                                │    │
│  │  • aggregations                                                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    OpenSearch Dashboards                            │    │
│  │                    (Port 5601)                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Observability Stack                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │ Prometheus  │  │   Grafana   │  │   Alert     │                         │
│  │ (Port 9090) │  │ (Port 3000) │  │  Manager    │                         │
│  └─────────────┘  └─────────────┘  └─────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

| Component | Technology | Port | Description |
|-----------|------------|------|-------------|
| **Producer** | Python/httpx | 8000 | SSE client, Kafka producer |
| **Kafka** | KRaft (no ZooKeeper) | 9092 | Event streaming platform |
| **Consumer** | Python/confluent-kafka | 8001 | Kafka consumer, OpenSearch indexer |
| **OpenSearch** | OpenSearch 2.17 | 9200 | Search and analytics engine |
| **Prometheus** | Prometheus | 9090 | Metrics collection |
| **Grafana** | Grafana | 3000 | Metrics visualization |

## Data Flow

```
Wikimedia SSE → Producer → Kafka → Consumer → OpenSearch
                                    ↓
                              Prometheus → Grafana
```

## Kafka Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| Bootstrap Servers | `kafka:9092` | Kafka broker address |
| Topic | `wikimedia.recentchanges` | Main topic |
| DLQ Topic | `wikimedia.dlq` | Dead letter queue |
| Partitions | 3 | Parallel processing |
| Replication Factor | 1 | Single node (dev) |

## Consumer Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| Group ID | `opensearch-consumer` | Consumer group |
| Auto Offset Reset | `earliest` | Start from beginning |
| Enable Auto Commit | `false` | Manual commit |
| Max Poll Interval | `300000` | 5 minutes |

## Index Mapping

```json
{
  "mappings": {
    "properties": {
      "id": { "type": "keyword" },
      "type": { "type": "keyword" },
      "namespace": { "type": "integer" },
      "title": { "type": "text", "fields": { "keyword": { "type": "keyword" } } },
      "user": { "type": "keyword" },
      "timestamp": { "type": "date" },
      "comment": { "type": "text" },
      "minor": { "type": "boolean" },
      "bot": { "type": "boolean" },
      "length": { "type": "object", "properties": {
        "old": { "type": "integer" },
        "new": { "type": "integer" }
      }},
      "revision": { "type": "object", "properties": {
        "old": { "type": "keyword" },
        "new": { "type": "keyword" }
      }}
    }
  }
}
```

## Error Handling

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Producer   │     │   Kafka     │     │  Consumer   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │ SSE Error         │ Partition Error   │ Indexing Error
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Reconnect  │     │  Retry      │     │  DLQ        │
│  (exponential│    │  (3 times)  │     │  (dead letter│
│   backoff)  │     │             │     │   queue)    │
└─────────────┘     └─────────────┘     └─────────────┘
```

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Kafka Mode | KRaft | No ZooKeeper dependency |
| Consumer Commit | Manual | At-least-once delivery |
| Idempotency | Revision ID | Prevent duplicate indexing |
| Error Handling | DLQ | Don't lose bad messages |
| Monitoring | Prometheus + Grafana | Industry standard |
| Security | Disabled (dev) | Simplified local development |

## Security Considerations

- ⚠️ OpenSearch security plugin disabled
- ⚠️ No Kafka authentication
- ⚠️ Grafana default credentials
- ✅ Detailed security upgrade guide provided
