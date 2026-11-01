# Security Policy — Python Wikimedia Kafka OpenSearch

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public GitHub issue
2. Email the maintainers directly
3. Include detailed description and reproduction steps
4. Allow time for a fix before public disclosure

## Security Measures

### Authentication & Authorization

| Feature | Implementation | Status |
|---------|---------------|--------|
| OpenSearch Auth | Disabled (dev) | ⚠️ Dev only |
| Kafka Auth | None (dev) | ⚠️ Dev only |
| Grafana Auth | Default credentials | ⚠️ Dev only |
| API Keys | Environment variables | ✅ Implemented |

### Data Protection

| Feature | Implementation | Status |
|---------|---------------|--------|
| HTTPS | TLS termination | ⚠️ Optional |
| Data Encryption | At rest (optional) | ⚠️ Optional |
| API Keys | Environment variables | ✅ Implemented |
| Secrets | Docker secrets | ✅ Implemented |

### Network Security

| Feature | Implementation | Status |
|---------|---------------|--------|
| Network Isolation | Docker networks | ✅ Implemented |
| Port Exposure | Internal only | ✅ Implemented |
| Firewall Rules | Host-based | ⚠️ Optional |

## Security Configuration

### Environment Variables

```bash
# Required for production
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=SCRAM-SHA-512
KAFKA_SASL_USERNAME=<username>
KAFKA_SASL_PASSWORD=<password>

# OpenSearch
OPENSEARCH_SECURITY=true
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=<password>
OPENSEARCH_SSL=true

# Grafana
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=<password>
```

### OpenSearch Security

```yaml
# opensearch.yml
plugins.security.ssl.http.enabled: true
plugins.security.ssl.transport.enforce_hostname_verification: false
plugins.security.authcz.admin_dn:
  - CN=kirk,OU=client,O=client,L=test,C=de
```

### Kafka Security

```properties
# server.properties
listeners=SASL_SSL://0.0.0.0:9093
security.inter.broker.protocol=SASL_SSL
sasl.mechanism.inter.broker.protocol=SCRAM-SHA-512
ssl.keystore.location=/path/to/kafka.server.keystore.jks
ssl.truststore.location=/path/to/kafka.server.truststore.jks
```

## Dependency Security

### Regular Updates

```bash
# Check for vulnerable dependencies
pip-audit
safety check

# Update dependencies
pip install --upgrade -r requirements.txt
```

### Security Scanning

```bash
# Bandit (Python security linter)
bandit -r producer/ consumer/

# Safety (dependency vulnerabilities)
safety check --full-report
```

## Data Security

### Wikimedia Data

- Respect Wikimedia Terms of Service
- Don't store personal data
- Implement data retention policies
- Use data for intended purposes only

### OpenSearch Data

- Encrypt data at rest
- Implement access controls
- Regular backups
- Monitor access logs

## Rate Limiting

```python
# Producer rate limiting
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=100, period=60)
def produce_event(event):
    # Produce event to Kafka
    pass
```

## Logging & Monitoring

### Security Events

```python
import logging

logger = logging.getLogger(__name__)

# Log security events
logger.warning("authentication_failed",
    extra={
        "user_id": user_id,
        "ip_address": ip_address,
        "timestamp": datetime.now().isoformat()
    }
)
```

### Audit Trail

- All API calls logged
- Authentication attempts tracked
- Data access logged
- Configuration changes recorded

## Security Checklist

### Pre-Deployment

- [ ] Enable OpenSearch security
- [ ] Configure Kafka authentication
- [ ] Change default credentials
- [ ] Enable TLS/SSL
- [ ] Implement rate limiting
- [ ] Update dependencies
- [ ] Security scan passed

### Post-Deployment

- [ ] Monitor security logs
- [ ] Review access patterns
- [ ] Check for vulnerabilities
- [ ] Update dependencies regularly
- [ ] Rotate secrets periodically

## Contact

For security concerns, contact the maintainers directly.
