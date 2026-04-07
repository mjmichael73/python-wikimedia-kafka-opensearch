# Wikimedia → Kafka → OpenSearch (Python)

A small **end-to-end streaming demo**: a Python producer reads the public [Wikimedia recent change Server-Sent Events (SSE) stream](https://stream.wikimedia.org/), publishes JSON events to **Apache Kafka**, and a Python consumer indexes those documents into **OpenSearch**. Everything is wired together with **Docker Compose** for a one-command local stack.

> **Not for production.** Security plugins are disabled on OpenSearch and Dashboards for simplicity. Use this for learning and local development only.

## Architecture

```mermaid
flowchart LR
    WM[Wikimedia SSE API]
    P[Producer Python]
    K[Kafka broker]
    C[Consumer Python]
    OS[(OpenSearch cluster)]
    DB[OpenSearch Dashboards]
    PR[Prometheus]
    GF[Grafana]

    WM -->|recentchange events| P
    P -->|wikimedia.recentchange| K
    K --> C
    C -->|index documents| OS
    DB -->|queries / UI| OS
    P -->|/metrics| PR
    C -->|/metrics| PR
    GF -->|queries| PR
```

| Piece | Role |
|--------|------|
| **Producer** (`producer/`) | `GET` SSE from `stream.wikimedia.org`, parse JSON, produce to topic `wikimedia.recentchange`. JSON **logs**, **`/healthz`** / **`/ready`** / **`/metrics`** on `OBS_HTTP_PORT`. |
| **Kafka** | Single-node KRaft mode — Docker image **`apache/kafka:3.9.0`**. Topic has 3 partitions (broker default). |
| **Consumer** (`consumer/`) | Subscribe with **`enable_auto_commit=False`**, index to OpenSearch, then **commit offsets**; DLQ by default. JSON **logs** and the same **observability HTTP** endpoints as the producer. |
| **OpenSearch** | Two nodes — **`opensearchproject/opensearch:2.17.1`**; data in named volumes. |
| **OpenSearch Dashboards** | **`opensearchproject/opensearch-dashboards:2.17.1`** on port **5601**. |
| **Prometheus** | **`prom/prometheus:v2.55.1`**; scrapes app **`/metrics`** (`monitoring/prometheus/prometheus.yml`). UI on port **9090**. |
| **Grafana** | **`grafana/grafana:11.3.0`** on port **3000**; **Prometheus** datasource and provisioned dashboards (`monitoring/grafana/`). Default login **`admin` / `admin`** (override via env). |

Compose services use **pinned tags** (no `:latest`); see the comment at the top of **`docker-compose.yml`** when upgrading.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/) v2
- Enough RAM for OpenSearch (two JVMs at 512 MiB each in the default compose file, plus Kafka and Python containers). **~4 GiB host RAM** is a comfortable minimum.

## Quick start

**Recommended (clean volumes + rebuild + detach):**

```bash
make up_clean
```

**Equivalent without Make:**

```bash
docker compose down --remove-orphans --volumes
docker compose up --build -d
```

**Other Make targets:**

| Target | Purpose |
|--------|---------|
| `make up` | Start stack without removing volumes |
| `make down` | Stop stack, keep volumes |
| `make clean` | Stop and remove containers **and** volumes |
| `make ps` | Show running services |

### Compose health and startup order

`docker-compose.yml` defines **healthchecks** so Compose can wait for dependencies before starting the Python apps:

| Service | Health check |
|---------|----------------|
| **broker** | `kafka-broker-api-versions.sh --bootstrap-server broker:9092` (KRaft broker accepting clients). |
| **opensearch-node1** / **opensearch-node2** | HTTP `/_cluster/health`; status must be **green** or **yellow** (cluster usable for indexing). |

**`depends_on`** with `condition: service_healthy`:

- **producer-app** starts only after **broker** is healthy.
- **consumer-app** starts only after **broker**, **opensearch-node1**, and **opensearch-node2** are all healthy.

`start_period` / `retries` on those healthchecks allow Kafka and the two-node OpenSearch cluster time to finish booting. The producer and consumer still contain **in-app retry loops** for transient failures after startup (see `producer/main.py` and `consumer/main.py`).

Inspect status: `docker compose ps` (shows `healthy` / `starting` in the **State** column when supported).

## Service endpoints (host machine)

| Service | URL / host |
|---------|------------|
| OpenSearch REST | http://localhost:9200 |
| OpenSearch Dashboards | http://localhost:5601 |
| Producer observability | http://localhost:**8080** — `GET /healthz` (liveness), `GET /ready` (503 until Kafka client is ready), `GET /metrics` (Prometheus) |
| Consumer observability | http://localhost:**8081** — same paths; `/ready` returns 503 until Kafka consumer + OpenSearch + optional DLQ producer are initialized |
| Prometheus | http://localhost:**9090** — targets, graph UI, `/metrics` self-scrape |
| Grafana | http://localhost:**3000** — open **Dashboards** for **Wikimedia pipeline** and **PWKO — Scrape health** (loaded from `monitoring/grafana/dashboards/`). |
| Kafka | `localhost:9092` is **not** published by default; clients run **inside** the compose network and use `broker:9092` |

Host ports **`8080`** / **`8081`** are configurable via `PRODUCER_OBS_HOST_PORT` and `CONSUMER_OBS_HOST_PORT` (see `.env.example`). Inside each app container the server listens on **`OBS_HTTP_PORT`** (default `8080`). **`PROMETHEUS_HOST_PORT`** (default **9090**) and **`GRAFANA_HOST_PORT`** (default **3000**) control Prometheus and Grafana.

## Verify the pipeline

1. **Cluster health**

   ```bash
   curl -s http://localhost:9200/_cluster/health?pretty
   ```

2. **Document count** (after the consumer has run a short while)

   ```bash
   curl -s "http://localhost:9200/wikimedia-changes/_count?pretty"
   ```

3. **Sample search** (titles containing “Python”, for example)

   ```bash
   curl -s "http://localhost:9200/wikimedia-changes/_search?q=title:Python&pretty" | head
   ```

4. In **OpenSearch Dashboards** (http://localhost:5601), create a data view / index pattern for `wikimedia-changes` (or the value of `OPENSEARCH_INDEX` if you changed it) and use **Discover**.

## Configuration (environment variables)

Tunables are read from the process environment. Defaults match the previous hard-coded values, so `docker compose up` works with no `.env` file.

**Docker Compose:** `producer-app` and `consumer-app` receive variables from the `environment` section in `docker-compose.yml`, which uses `${VAR:-default}` substitution. Compose automatically loads a **`.env`** file in the project root (if present) for that substitution—so you can copy `.env.example` to `.env` and edit values there without changing the compose file.

**Local runs** (without Compose): export the same variable names before `python main.py`, or use a tool of your choice to load `.env`.

| Variable | Apps | Default | Purpose |
|----------|------|---------|---------|
| `WIKIMEDIA_STREAM_URL` | Producer | `https://stream.wikimedia.org/v2/stream/recentchange` | Wikimedia SSE endpoint. |
| `WIKIMEDIA_HTTP_USER_AGENT` | Producer | *(see compose default)* | **Required** to be descriptive per [Wikimedia User-Agent policy](https://meta.wikimedia.org/wiki/User-Agent_policy); generic `python-requests/...` is blocked (**403**). Default string identifies this demo; set your project URL in `.env` for serious use. |
| `WIKIMEDIA_SSE_RECONNECT_DELAY_SECONDS` | Producer | `5` | Sleep before reconnecting after the SSE stream closes or a connection error (Wikimedia often ends long-lived connections). |
| `KAFKA_BOOTSTRAP_SERVERS` | Both | `broker:9092` | Kafka brokers (comma-separated `host:port`). Use `broker:9092` inside this Compose network. |
| `KAFKA_TOPIC` | Both | `wikimedia.recentchange` | Topic name. |
| `KAFKA_CONSUMER_GROUP` | Consumer | `wikimedia-consumer-group` | Kafka consumer group id. |
| `KAFKA_DLQ_TOPIC` | Consumer | `wikimedia.recentchange.dlq` | Topic for poison / failed documents (JSON envelope with error + payload). Set to empty to disable DLQ (offset is still committed so the consumer does not stall). |
| `OPENSEARCH_HOST` | Consumer | `opensearch-node1` | OpenSearch hostname (compose service name). |
| `OPENSEARCH_PORT` | Consumer | `9200` | OpenSearch HTTP port. |
| `OPENSEARCH_INDEX` | Consumer | `wikimedia-changes` | Target index (created if missing). |
| `OPENSEARCH_USE_SSL` | Consumer | `false` | Use HTTPS to OpenSearch (**required** when the security plugin terminates TLS on the REST port). |
| `OPENSEARCH_USER` | Consumer | *(empty)* | HTTP basic-auth username when security is enabled. |
| `OPENSEARCH_PASSWORD` | Consumer | *(empty)* | HTTP basic-auth password (pair with **`OPENSEARCH_USER`**). |
| `OPENSEARCH_VERIFY_CERTS` | Consumer | `true` when **`OPENSEARCH_USE_SSL`** is set | Whether to verify the server TLS certificate. |
| `OPENSEARCH_CA_CERTS` | Consumer | *(empty)* | Path **inside the consumer container** to a PEM CA bundle (enables verification of a private CA). |
| `OPENSEARCH_SSL_ASSERT_HOSTNAME` | Consumer | `true` | Certificate hostname verification; set **`false`** only when the cert’s SAN/CN does not match **`OPENSEARCH_HOST`** (common in Compose without per-service certs). |
| `KAFKA_CLIENT_RETRY_MAX_ATTEMPTS` | Both | `10` | Max attempts to create Kafka producer/consumer. |
| `KAFKA_CLIENT_RETRY_DELAY_SECONDS` | Both | `5` | Sleep between Kafka connection retries (seconds). |
| `OPENSEARCH_RETRY_MAX_ATTEMPTS` | Consumer | `20` | Max attempts to connect and prepare the index. |
| `OPENSEARCH_RETRY_DELAY_SECONDS` | Consumer | `5` | Sleep between OpenSearch retries (seconds). |
| `LOG_LEVEL` | Both | `INFO` | Root log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `OBS_HTTP_PORT` | Both | `8080` | Port inside the container for health + Prometheus metrics HTTP server. |
| `PRODUCER_OBS_HOST_PORT` | Compose | `8080` | Published host port for **producer** observability (`host:OBS_HTTP_PORT`). |
| `CONSUMER_OBS_HOST_PORT` | Compose | `8081` | Published host port for **consumer** observability. |
| `PROMETHEUS_HOST_PORT` | Compose | `9090` | Prometheus UI and API on the host. |
| `GRAFANA_HOST_PORT` | Compose | `3000` | Grafana UI on the host. |
| `GRAFANA_ADMIN_USER` | Compose | `admin` | Grafana admin username. |
| `GRAFANA_ADMIN_PASSWORD` | Compose | `admin` | Grafana admin password (**change for anything beyond local demo**). |

Shared template: **[`.env.example`](.env.example)**. Copy to `.env` to override; `.env` is gitignored.

Verification commands above use the default index name `wikimedia-changes`; if you set `OPENSEARCH_INDEX`, substitute that name in URLs.

### OpenSearch mapping and index template

Wikimedia [recentchange](https://github.com/wikimedia/mediawiki-event-schemas/blob/master/jsonschema/mediawiki/recentchange/current.yaml) events are indexed with **explicit field types** (for example `title` as `text` with a `keyword` subfield for sorting/aggregations, `meta.dt` as `date`, filters as `keyword`/`boolean`/`integer`, and `log_params` stored but not mapped per-field to avoid noisy dynamic objects).

- **Composable index template** `wikimedia-recentchange` matches new indices named `wikimedia-*` so extra indices created later inherit the same settings/mappings.
- **New index creation** from the consumer uses the same JSON payload as the template (`consumer/wikimedia_mappings.py`), so the default `OPENSEARCH_INDEX` gets the mapping even before any document is indexed.
- **`dynamic` is `false`**: fields not declared in the mapping remain in `_source` only (fewer surprise mappings, typically smaller and more predictable indexes). Extend `wikimedia_mappings.py` if you need to query new properties.

If the index already existed from an older run (empty or dynamic mapping), OpenSearch will **not** retrofit this mapping: delete the index (or reindex) and restart the consumer—see **Troubleshooting**.

### Document identity (`_id` in OpenSearch)

Each indexed document gets an explicit `_id` so missing Wikimedia ids do not break indexing, and natural keys are preferred over Kafka position where possible:

1. **`meta.id`** — WMF event UUID (when `meta` is present and `meta.id` is non-empty). Prefer this for stable, idempotent re-indexing of the same event and to avoid cross-event collisions on `id` (rcid) in odd payloads.
2. **`id`** — MediaWiki recentchange id (rcid) when set (including `0` if it ever appears).
3. **Fallback** — `kafka:<topic>:<partition>:<offset>` from the consumer record so every consumed message has a unique key even when both ids are absent.

Replays of the **same** event (same `meta.id` or same `id`) overwrite the same OpenSearch document, which is usually desirable; distinct Kafka records with missing ids each get a distinct fallback `_id`.

### Consumer semantics (commits and dead-letter queue)

The consumer disables Kafka’s **auto-commit** and, after each message, calls **`commit()`** with an explicit **`OffsetAndMetadata`** for that record’s `TopicPartition` (next offset = `message.offset + 1`). Successful OpenSearch indexing and the “skip after handling failure” paths both advance the offset so partitions do not hang indefinitely.

If indexing (or validation) raises, the consumer **publishes a JSON envelope** to **`KAFKA_DLQ_TOPIC`** (default `wikimedia.recentchange.dlq`): error string and type, source `topic` / `partition` / `offset`, record `timestamp`, optional `key`, and the **`document`** body. Only after a successful DLQ publish does it commit when the main path failed. If DLQ **publish** fails, the offset is **not** committed so the message is retried.

Set **`KAFKA_DLQ_TOPIC`** to an empty string to turn off DLQ publishing; failed messages are logged and the offset is still committed (no infinite retry on poison payloads).

### Observability (logs, health, Prometheus)

- **Structured logging:** Both apps log **one JSON object per line** to stdout (`timestamp`, `level`, `logger`, `message`, `service`, `event`, and any `extra={...}` fields). `PYTHONUNBUFFERED=1` is set in Compose for timely log shipping.
- **HTTP:** A small background **`ThreadingHTTPServer`** serves **`/healthz`** and **`/health`** (always 200 if the process is up), **`/ready`** / **`/readiness`** (503 until the app finishes startup dependencies—Kafka producer ready on the producer; consumer + OpenSearch + DLQ producer ready on the consumer), and **`/metrics`** in the **Prometheus text exposition format** (`prometheus_client`).
- **Metrics (examples):** `wikimedia_producer_events_total`, `wikimedia_producer_errors_total`, `wikimedia_consumer_indexed_total`, `wikimedia_consumer_dlq_total`, `wikimedia_consumer_process_errors_total`, `wikimedia_consumer_offsets_committed_total`.

Implementation lives in **`producer/observability.py`** and **`consumer/observability.py`**.

**Prometheus + Grafana:** Compose services **`prometheus`** and **`grafana`** scrape the app **`/metrics`** endpoints on the Docker network (`producer-app:8080`, `consumer-app:8080`). Dashboards are **JSON** files auto-loaded at Grafana start:

| Dashboard | File | Contents (summary) |
|-----------|------|---------------------|
| **Wikimedia pipeline (Kafka / OpenSearch)** | `monitoring/grafana/dashboards/pwko-pipeline.json` | Producer throughput & error rates; consumer index/offset rates; DLQ and process-error totals; `up` for scrape targets. |
| **PWKO — Scrape health** | `monitoring/grafana/dashboards/pwko-scrape-health.json` | Scrape latency and a table of target **up** state. |

After `docker compose up`, open Grafana → **Dashboards** (folder *General*, tags `pwko`). Edit the JSON under `monitoring/grafana/dashboards/` and restart Grafana or use **Save** (with **allowUiUpdates** enabled in provisioning) to iterate.

## OpenSearch secure mode (TLS and auth)

The default stack is intentionally **insecure for teaching**: both OpenSearch nodes set **`plugins.security.disabled=true`**, **skip demo security material** (`DISABLE_INSTALL_DEMO_CONFIG=true`), and **OpenSearch Dashboards** sets **`DISABLE_SECURITY_DASHBOARDS_PLUGIN=true`**. REST calls use **plaintext HTTP** on port **9200** inside the network; the consumer uses **`OPENSEARCH_USE_SSL=false`** and no credentials.

Moving toward **TLS + authentication** is a separate path: **do not** flip these flags on an index volume that was created with security off and expect a smooth upgrade—plan for **new data directories** (or a [snapshot restore](https://opensearch.org/docs/latest/migrating-to-opensearch/snapshot-restore/)) and follow **[OpenSearch security](https://docs.opensearch.org/latest/security/)** documentation for your target environment.

### 1. OpenSearch nodes (`opensearch-node1` / `opensearch-node2`)

In **`docker-compose.yml`**, for **each** OpenSearch service:

1. **Remove** the line **`plugins.security.disabled=true`** so the security plugin loads.
2. **Allow demo security configuration** (suitable **only** for lab / proof-of-concept): replace **`DISABLE_INSTALL_DEMO_CONFIG=true`** with **`DISABLE_INSTALL_DEMO_CONFIG=false`**, **or** delete that variable and rely on the image default so the demo installer can run.
3. Set an **initial admin password** as required by your image version (see [Installing OpenSearch with Docker](https://docs.opensearch.org/latest/install-and-configure/install-opensearch/docker/)). Many 2.x images expect **`OPENSEARCH_INITIAL_ADMIN_PASSWORD`** (strong password); behavior changed across minor releases, so confirm in the docs for **`opensearchproject/opensearch:2.17.1`** and check container logs if bootstrap fails.
4. **Inter-node TLS and transport** are part of a full secure cluster; the stock **demo configuration** often generates node and client certificates so the two-node cluster can form a quorum. For **production**, replace demo material with certificates from your PKI and audit **[security configuration files](https://docs.opensearch.org/latest/security/configuration/)** (`opensearch.yml`, `config.yml`, roles, etc.)—that is out of scope for this repo; treat the steps below as a **roadmap**, not a production hardening guide.

**REST becomes HTTPS** on **9200** once TLS is enabled. Update **healthchecks** from `curl http://127.0.0.1:9200/...` to **HTTPS**, for example:

```bash
curl -sf -u "$ADMIN_USER:$ADMIN_PASSWORD" --cacert /usr/share/opensearch/config/root-ca.pem "https://127.0.0.1:9200/_cluster/health"
```

Use **`curl -k`** only for quick debugging; prefer mounting the CA and verifying certs in real setups.

### 2. OpenSearch Dashboards (`opensearch-dashboards`)

1. **Stop disabling** the security integration: remove **`DISABLE_SECURITY_DASHBOARDS_PLUGIN: "true"`** (or set it to **`false`** if your image documents that explicitly).
2. Point **`OPENSEARCH_HOSTS`** at **`https://`** backends, e.g. `["https://opensearch-node1:9200","https://opensearch-node2:9200"]`.
3. Provide credentials the Dashboards process uses to talk to OpenSearch—see **[OpenSearch Dashboards Docker](https://docs.opensearch.org/latest/install-and-configure/install-dashboards/docker/)** for **`OPENSEARCH_USERNAME`**, **`OPENSEARCH_PASSWORD`**, and TLS-related settings (for example trusting the OpenSearch HTTP CA).

You will log in to the **5601** UI with a dashboard user defined in your security configuration (not necessarily the same as the **admin** transport user).

### 3. Python consumer (`consumer-app`)

The consumer’s OpenSearch client reads TLS and auth from the environment (see the table in **Configuration**). For a **demo** HTTPS endpoint with a **self-signed** cert and **basic auth** from inside Compose, typical settings are:

| Variable | Example (demo / dev only) |
|----------|---------------------------|
| **`OPENSEARCH_USE_SSL`** | `true` |
| **`OPENSEARCH_USER`** | Administrative or REST user allowed to create indices |
| **`OPENSEARCH_PASSWORD`** | Matching password |
| **`OPENSEARCH_VERIFY_CERTS`** | `false` *temporary* shortcut if you do not mount a CA (**prefer** `true` + **`OPENSEARCH_CA_CERTS`**) |
| **`OPENSEARCH_SSL_ASSERT_HOSTNAME`** | `false` if the certificate is issued for a hostname other than **`OPENSEARCH_HOST`** |

Mount your CA PEM into the consumer container (read-only volume) and set **`OPENSEARCH_CA_CERTS`** to that path when you move past ad hoc `-k`-style setups.

### 4. Host-side curls and bookmarks

Replace **`http://localhost:9200`** with **`https://localhost:9200`**, pass **`-u user:pass`**, and add **`--cacert`** (or **`curl -k`** only for local experiments). Dashboards: **`https://localhost:5601`** once TLS is enabled there as well (exact URL depends on how you terminate TLS in front of Dashboards).

### 5. Kafka, Prometheus, and Grafana

This “secure mode” section only covers **OpenSearch + Dashboards + consumer indexing**. **Kafka** still runs **PLAINTEXT** in the default compose file; **Prometheus** scrapes **`http://.../metrics`** on the apps. Locking those down (TLS, SASL, network policies, reverse proxies) is a separate exercise.

---

**Summary:** keep the **default compose** for learning; fork the compose file (or maintain a private override) for **security-enabled OpenSearch**, wire **Dashboards** to **HTTPS + auth**, and set **`OPENSEARCH_*`** on **`consumer-app`** so **`opensearch-py`** uses **HTTPS** and **basic auth**. For anything beyond lab demo certificates, follow the official **security** and **installation** guides and your organization’s PKI and secrets practices.

## Project layout

```
├── .env.example          # Documented defaults; copy to `.env` to customize
├── docker-compose.yml    # Full stack + Prometheus + Grafana + test-runner (profile test)
├── Dockerfile.test       # Python 3.11 test image (requirements-dev.txt)
├── Makefile              # up_clean, up, down, clean, ps, lint, lint-docker, test, test-integration
├── .github/workflows/ci.yml  # GitHub Actions: lint (ruff/black/mypy), Docker build, make test + test-integration
├── requirements-dev.txt  # pytest, testcontainers, ruff, black, mypy, app libs for tests
├── tests/                # Unit + integration (Testcontainers) tests
├── monitoring/
│   ├── prometheus/
│   │   └── prometheus.yml   # Scrape producer-app + consumer-app :8080/metrics
│   └── grafana/
│       ├── dashboards/       # Provisioned dashboard JSON (pwko-*.json)
│       └── provisioning/     # Datasource + dashboard providers
├── producer/
│   ├── Dockerfile
│   ├── main.py
│   ├── observability.py   # JSON logging + health/metrics HTTP
│   └── requirements.txt   # kafka-python, prometheus_client, requests, sseclient-py
└── consumer/
    ├── Dockerfile
    ├── document_id.py     # OpenSearch _id logic (used by main + unit tests)
    ├── main.py
    ├── observability.py
    ├── wikimedia_mappings.py  # Index template + mapping for recentchange
    └── requirements.txt  # kafka-python, opensearch-py, prometheus_client
```

Both apps use **Python 3.11** slim images and mount their source directories for quick iteration.

## Testing

**Linting and types (host Python):** after `pip install -r requirements-dev.txt`, run `make lint` (**ruff** check, **black** `--check`, **mypy** per app directory so `producer/main.py` and `consumer/main.py` are not merged as duplicate `main` modules). To run the same checks inside the test image: `make lint-docker` (builds/runs `test-runner`).

**CI:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs lint on the runner, then **`docker compose build`** for **`producer-app`**, **`consumer-app`**, and **`test-runner`**, then **`make test`** and **`make test-integration`**.

Tests run **inside Docker** via the Compose service **`test-runner`** (profile **`test`**) so the runtime matches the apps and **integration** tests can use [Testcontainers](https://testcontainers.com/) against the host Docker daemon.

| Command | Purpose |
|---------|---------|
| `make lint` | Ruff, Black (check), mypy (`producer/` and `consumer/` separately). |
| `make lint-docker` | Same as `make lint` inside the `test-runner` container. |
| `make test` | Unit tests only (`pytest` without `--integration`; fast). |
| `make test-integration` | All tests including integration (**Kafka + OpenSearch** containers; needs a working Docker socket). |
| `make test-build` | Build the `test-runner` image only. |

Equivalent Compose invocations:

```bash
docker compose --profile test run --rm test-runner pytest tests/ -v
docker compose --profile test run --rm test-runner pytest tests/ -v --integration
```

The **`test-runner`** service mounts the repo at **`/app`**, the Docker socket at **`/var/run/docker.sock`**, and sets **`TESTCONTAINERS_HOST_OVERRIDE=host.docker.internal`** with **`host.docker.internal:host-gateway`** so Testcontainers-published ports are reachable from inside the test container on Linux.

Dev dependencies are listed in **`requirements-dev.txt`**; the image is defined by **`Dockerfile.test`**. Running `pytest` directly on the host is possible if you install `requirements-dev.txt` locally, but **`make test`** is the supported path.

## Troubleshooting

- **Mapping did not update after upgrading** — Indices keep their original mapping. For example: `curl -X DELETE "http://localhost:9200/wikimedia-changes"` (adjust if you changed `OPENSEARCH_INDEX`), then `docker compose restart consumer-app` so the index is recreated with the explicit mapping.
- **Consumer logs “OpenSearch not available”** — Compose should wait until both OpenSearch nodes report green/yellow before the consumer starts; if you still see this, the cluster may be slow or unhealthy—check `docker compose ps` and `curl -s http://localhost:9200/_cluster/health?pretty`. The consumer also retries in code.
- **No documents in OpenSearch** — Confirm `consumer-app` is running (`docker compose ps` or `make ps`). Confirm Wikimedia stream is reachable from the producer container.
- **Producer logs `403 Forbidden` from `stream.wikimedia.org`** — Wikimedia requires a [descriptive `User-Agent`](https://meta.wikimedia.org/wiki/User-Agent_policy). This stack sets **`WIKIMEDIA_HTTP_USER_AGENT`** in **`docker-compose.yml`**; override in **`.env`** with your project or contact URL if needed.
- **Out of memory** — Reduce `OPENSEARCH_JAVA_OPTS` in `docker-compose.yml` or run a single OpenSearch node for lighter setups.
- **Producer observability URL not reachable** — The producer **reconnects** when the Wikimedia SSE stream closes (common) or after network errors; if it still never listens on **8080**, check `docker compose logs producer-app` and confirm the process is not stuck creating the Kafka client. The consumer stays up longer and is easier to probe on **8081**.
- **Integration tests fail inside `test-runner`** — Ensure the Docker socket is mounted (Compose does this) and that **`host.docker.internal` resolves (Linux: `extra_hosts: host-gateway`)**. Testcontainers needs permission to create sibling containers.

Contributions that tackle items above are welcome if you fork or extend this repository.
