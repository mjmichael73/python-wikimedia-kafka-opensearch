"""
OpenSearch index settings + mappings for Wikimedia EventStreams
`mediawiki/recentchange` events.

Schema reference: https://github.com/wikimedia/mediawiki-event-schemas/blob/master/jsonschema/mediawiki/recentchange/current.yaml
and common meta: jsonschema/common/1.0.0.yaml

`dynamic` is false so fields not listed here stay in _source only (better mapping
control and index size); adjust the mapping if you need to query new fields.
"""

WIKIMEDIA_INDEX_TEMPLATE_NAME = "wikimedia-recentchange"
WIKIMEDIA_INDEX_PATTERNS = ["wikimedia-*"]


def wikimedia_recentchange_index_spec():
    """Settings and mappings shared by the composable index template and explicit index create."""
    return {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 1,
            }
        },
        "mappings": {
            "dynamic": False,
            "properties": {
                "$schema": {"type": "keyword", "ignore_above": 1024},
                "id": {"type": "long"},
                "type": {"type": "keyword"},
                "title": {
                    "type": "text",
                    "fields": {
                        "keyword": {"type": "keyword", "ignore_above": 8191},
                    },
                },
                "namespace": {"type": "integer"},
                "comment": {"type": "text"},
                "parsedcomment": {"type": "text"},
                "timestamp": {"type": "long"},
                "user": {"type": "keyword"},
                "bot": {"type": "boolean"},
                "server_url": {"type": "keyword", "ignore_above": 2048},
                "server_name": {"type": "keyword"},
                "server_script_path": {"type": "keyword"},
                "wiki": {"type": "keyword"},
                "minor": {"type": "boolean"},
                "patrolled": {"type": "boolean"},
                "length": {
                    "type": "object",
                    "properties": {
                        "old": {"type": "integer"},
                        "new": {"type": "integer"},
                    },
                },
                "revision": {
                    "type": "object",
                    "properties": {
                        "old": {"type": "long"},
                        "new": {"type": "long"},
                    },
                },
                "log_id": {"type": "long"},
                "log_type": {"type": "keyword"},
                "log_action": {"type": "keyword"},
                "log_params": {"type": "object", "enabled": False},
                "log_action_comment": {"type": "text"},
                "meta": {
                    "type": "object",
                    "properties": {
                        "uri": {"type": "keyword", "ignore_above": 8192},
                        "request_id": {"type": "keyword"},
                        "id": {"type": "keyword"},
                        "dt": {
                            "type": "date",
                            "format": "strict_date_optional_time||epoch_millis",
                        },
                        "domain": {"type": "keyword"},
                        "stream": {"type": "keyword"},
                        "topic": {"type": "keyword"},
                        "partition": {"type": "integer"},
                        "offset": {"type": "long"},
                    },
                },
            },
        },
    }


def wikimedia_recentchange_index_template_body():
    return {
        "index_patterns": WIKIMEDIA_INDEX_PATTERNS,
        "priority": 100,
        "template": wikimedia_recentchange_index_spec(),
    }


def wikimedia_recentchange_create_index_body():
    return wikimedia_recentchange_index_spec()
