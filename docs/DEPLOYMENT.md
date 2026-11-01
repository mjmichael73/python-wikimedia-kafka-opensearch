# Deployment Guide — Python Wikimedia Kafka OpenSearch

## Overview

This guide covers deploying Python Wikimedia Kafka OpenSearch to production using Docker Compose or Kubernetes.

## Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Kafka cluster (or managed service)
- OpenSearch cluster (or managed service)

## Environment Variables

Create `.env.production`:

```bash
# Kafka
KAFKA_BOOTSTRAP_SERVERS=broker1:9092,broker2:9092
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=SCRAM-SHA-512
KAFKA_SASL_USERNAME=<username>
KAFKA_SASL_PASSWORD=<password>

# OpenSearch
OPENSEARCH_URL=https://opensearch1:9200,https://opensearch2:9200
OPENSEARCH_SECURITY=true
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=<password>
OPENSEARCH_SSL=true

# Producer
PRODUCER_TOPIC=wikimedia.recentchanges
PRODUCER_BATCH_SIZE=16384
PRODUCER_LINGER_MS=10

# Consumer
CONSUMER_GROUP_ID=opensearch-consumer
CONSUMER_TOPIC=wikimedia.recentchanges
CONSUMER_AUTO_OFFSET_RESET=earliest
```

## Docker Compose Deployment

### 1. Build Images

```bash
# Build producer
docker build -t wikimedia-producer -f producer/Dockerfile .

# Build consumer
docker build -t wikimedia-consumer -f consumer/Dockerfile .
```

### 2. Start Services

```bash
# Start all services
docker compose -f docker-compose.prod.yml up -d

# Check status
docker compose ps

# View logs
docker compose logs -f producer
docker compose logs -f consumer
```

### 3. Configure Kafka

```bash
# Create topic
docker compose exec kafka kafka-topics \
  --create \
  --topic wikimedia.recentchanges \
  --partitions 3 \
  --replication-factor 3 \
  --bootstrap-server kafka:9092

# Create DLQ topic
docker compose exec kafka kafka-topics \
  --create \
  --topic wikimedia.dlq \
  --partitions 3 \
  --replication-factor 3 \
  --bootstrap-server kafka:9092
```

### 4. Configure OpenSearch

```bash
# Create index
curl -X PUT "https://opensearch:9200/wikimedia-recentchanges" \
  -H "Content-Type: application/json" \
  -u admin:password \
  -k -d '{
    "mappings": {
      "properties": {
        "id": {"type": "keyword"},
        "type": {"type": "keyword"},
        "title": {"type": "text"},
        "timestamp": {"type": "date"}
      }
    }
  }'
```

## Kubernetes Deployment

### 1. Create Namespace

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: wikimedia-streaming
```

### 2. Deploy Producer

```yaml
# producer-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wikimedia-producer
  namespace: wikimedia-streaming
spec:
  replicas: 2
  selector:
    matchLabels:
      app: wikimedia-producer
  template:
    metadata:
      labels:
        app: wikimedia-producer
    spec:
      containers:
      - name: producer
        image: wikimedia-producer:latest
        envFrom:
        - secretRef:
            name: wikimedia-secrets
        - configMapRef:
            name: wikimedia-config
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

### 3. Deploy Consumer

```yaml
# consumer-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wikimedia-consumer
  namespace: wikimedia-streaming
spec:
  replicas: 3
  selector:
    matchLabels:
      app: wikimedia-consumer
  template:
    metadata:
      labels:
        app: wikimedia-consumer
    spec:
      containers:
      - name: consumer
        image: wikimedia-consumer:latest
        envFrom:
        - secretRef:
            name: wikimedia-secrets
        - configMapRef:
            name: wikimedia-config
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

### 4. Apply Manifests

```bash
kubectl apply -f namespace.yaml
kubectl apply -f producer-deployment.yaml
kubectl apply -f consumer-deployment.yaml
```

## Health Checks

```bash
# Producer metrics
curl http://localhost:8000/metrics

# Consumer metrics
curl http://localhost:8001/metrics

# Kafka health
docker compose exec kafka kafka-broker-api-versions --bootstrap-server kafka:9092

# OpenSearch health
curl -k -u admin:password https://opensearch:9200/_cluster/health
```

## Monitoring

### Prometheus

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'wikimedia-producer'
    static_configs:
      - targets: ['producer:8000']
  - job_name: 'wikimedia-consumer'
    static_configs:
      - targets: ['consumer:8001']
```

### Grafana

Access Grafana at `http://localhost:3000` (default credentials: admin/admin)

Import dashboards:
- Kafka metrics
- OpenSearch metrics
- Application metrics

## Backup & Restore

### OpenSearch Backup

```bash
# Backup
curl -X POST "https://opensearch:9200/_snapshot/backup/snapshot_1" \
  -u admin:password -k

# Restore
curl -X POST "https://opensearch:9200/_snapshot/backup/snapshot_1/_restore" \
  -u admin:password -k
```

### Kafka Backup

```bash
# Export topics
docker compose exec kafka kafka-exporter \
  --bootstrap-server kafka:9092 \
  --output-file /backup/kafka-export.json
```

## Rollback

```bash
# Docker Compose
docker compose down
docker compose -f docker-compose.prev.yml up -d

# Kubernetes
kubectl rollout undo deployment/wikimedia-producer -n wikimedia-streaming
kubectl rollout undo deployment/wikimedia-consumer -n wikimedia-streaming
```

## Troubleshooting

See TROUBLESHOOTING.md for common issues.
