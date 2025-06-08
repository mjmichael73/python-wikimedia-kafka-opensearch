# Python Kafka and OpenSearch Producer and Consumer

### Description
This project uses Wikimedia stream as a source of events to create a simple producer and consumer in Python.

### How it works (Flow)
- The producer will receive streams from WikiMedia stream.
- The producer publishes streams to Apache Kafka broker.
- A consumer will connect to broker (Apache Kafka) and starts to consume streams and then will index them into OpenSearch.

### Technologies used:
- Python
- Docker and Docker Compose
- Apache Kafka as the broker
- OpenSearch as the Indexing Database

### How to run (Using Makefile):
Just run this command:

- make up_clean

### How to run (Without Makefile):

- docker compose up --build -d

### To visualize or run queries in OpenSearch:
- Either use OpenSearch REST API
- Or use OpenSearch Dashboard at: http://localhost:5601

### Notes:
- I have disabled security for simplicity.
- Do not use this project in the production environment.
