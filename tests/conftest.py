import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# consumer/*.py use absolute imports as in the Docker image (WORKDIR /app).
_ROOT = Path(__file__).resolve().parent.parent
_CONSUMER_DIR = str(_ROOT / "consumer")
if _CONSUMER_DIR not in sys.path:
    sys.path.insert(0, _CONSUMER_DIR)


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests (requires Docker)",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip_int = pytest.mark.skip(reason="pass --integration and Docker to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_int)


@pytest.fixture(scope="session")
def docker_available():
    """Fail fast with a clear message when integration tests cannot run."""
    try:
        import docker
    except ImportError as e:
        pytest.skip(f"docker SDK not installed: {e}")
    try:
        docker.from_env().ping()
    except Exception as e:
        pytest.skip(f"Docker daemon not reachable: {e}")


def normalize_kafka_bootstrap(server: str) -> str:
    if server.startswith("PLAINTEXT://"):
        return server.split("://", 1)[1]
    if server.startswith("SASL_"):
        return server.split("://", 1)[1]
    return server


def wait_opensearch_ready(host: str, port: int, timeout_s: float = 120.0) -> None:
    deadline = time.time() + timeout_s
    url = f"http://{host}:{port}/_cluster/health"
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                body = resp.read().decode()
                if '"status"' in body and ('"green"' in body or '"yellow"' in body):
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionResetError) as e:
            last_err = e
        time.sleep(2)
    raise RuntimeError(f"OpenSearch not ready at {url}: {last_err}")


@pytest.fixture(scope="module")
def kafka_bootstrap(docker_available):
    from testcontainers.kafka import KafkaContainer

    with KafkaContainer() as kafka:
        yield normalize_kafka_bootstrap(kafka.get_bootstrap_server())


@pytest.fixture(scope="module")
def opensearch_host_port(docker_available):
    from testcontainers.core.container import DockerContainer

    container = (
        DockerContainer("opensearchproject/opensearch:2.17.1")
        .with_env("discovery.type", "single-node")
        .with_env("plugins.security.disabled", "true")
        .with_env("DISABLE_INSTALL_DEMO_CONFIG", "true")
        .with_env("OPENSEARCH_JAVA_OPTS", "-Xms256m -Xmx256m")
        .with_exposed_ports(9200)
    )
    container.start()
    try:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(9200))
        wait_opensearch_ready(host, port)
        yield host, port
    finally:
        container.stop()
