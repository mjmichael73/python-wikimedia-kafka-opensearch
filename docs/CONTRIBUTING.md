# Contributing — Python Wikimedia Kafka OpenSearch

Thank you for your interest in contributing to Python Wikimedia Kafka OpenSearch!

## Getting Started

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Kafka CLI tools (optional)

### Development Setup

```bash
# Clone the repository
git clone <repository-url>
cd python-wikimedia-kafka-opensearch

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start development environment
docker compose up -d

# Run tests
pytest
```

## Project Structure

```
python-wikimedia-kafka-opensearch/
├── producer/              # Kafka producer
│   ├── __init__.py
│   ├── client.py         # SSE client
│   ├── transformer.py    # Event transformation
│   └── producer.py       # Kafka producer
├── consumer/              # Kafka consumer
│   ├── __init__.py
│   ├── consumer.py       # Kafka consumer
│   ├── transformer.py    # Message transformation
│   └── indexer.py        # OpenSearch indexer
├── tests/                 # Test files
├── docker-compose.yml    # Development environment
└── requirements.txt      # Python dependencies
```

## Development Guidelines

### Python Code Style

- Follow PEP 8 guidelines
- Use Black for code formatting
- Use flake8 for linting
- Use type hints

```bash
# Format code
black .

# Check linting
flake8 .

# Type checking
mypy .
```

### Kafka Best Practices

1. **Producer**
   - Use idempotent producer
   - Handle retries properly
   - Use appropriate batch size

2. **Consumer**
   - Manual offset commit
   - Handle rebalancing
   - Implement dead letter queue

3. **Error Handling**
   - Log all errors
   - Use structured logging
   - Implement circuit breaker

### Git Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Run tests: `pytest`
5. Commit: `git commit -m 'feat: Add amazing feature'`
6. Push: `git push origin feature/amazing-feature`
7. Open a pull request

### Commit Messages

Use conventional commits:

```
feat: Add new event transformer
fix: Resolve Kafka connection issue
docs: Update API documentation
test: Add unit tests for consumer
refactor: Simplify indexing logic
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=producer --cov=consumer

# Run specific test file
pytest tests/test_producer.py

# Run with verbose output
pytest -v
```

### Test Structure

```python
# tests/test_producer.py
import pytest
from producer import WikimediaProducer

class TestWikimediaProducer:
    def test_transform_event(self):
        producer = WikimediaProducer()
        event = {"id": 123, "type": "edit"}
        result = producer.transform_event(event)
        assert result["id"] == "123"
    
    @patch('confluent_kafka.Producer')
    def test_publish_event(self, mock_producer):
        producer = WikimediaProducer()
        producer.publish_event({"id": "123"})
        mock_producer.produce.assert_called_once()
```

## Pull Request Process

1. **Before submitting:**
   - [ ] Code follows project style guidelines
   - [ ] Tests pass locally
   - [ ] Documentation updated
   - [ ] No sensitive data committed

2. **PR Description:**
   - Clear description of changes
   - Reference related issues
   - Include test results

3. **Review Process:**
   - At least one maintainer approval
   - All CI checks pass
   - No merge conflicts

## Reporting Issues

When reporting issues, please include:

1. **Component affected**
   - Producer
   - Consumer
   - Kafka
   - OpenSearch

2. **Steps to reproduce**
   - Clear, numbered steps
   - Expected behavior
   - Actual behavior

3. **Logs/Screenshots**
   - Error messages
   - Kafka logs
   - OpenSearch logs

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Help each other learn

## Questions?

If you have questions:

1. Check the documentation
2. Search existing issues
3. Open a discussion issue
4. Contact maintainers

Thank you for contributing! 🎉
