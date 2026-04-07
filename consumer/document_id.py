"""Pure helpers for OpenSearch document identity (unit-test friendly, no side effects)."""


def opensearch_document_id(doc: dict, message, *, kafka_topic_fallback: str) -> str:
    """
    Stable OpenSearch _id: WMF meta.id (event UUID), else recentchange id (rcid),
    else kafka:<topic>:<partition>:<offset>.
    """
    meta = doc.get("meta")
    if isinstance(meta, dict):
        mid = meta.get("id")
        if mid is not None and str(mid).strip() != "":
            return str(mid)
    rid = doc.get("id")
    if rid is not None:
        return str(rid)
    topic = getattr(message, "topic", None) or kafka_topic_fallback
    partition = message.partition
    offset = message.offset
    return f"kafka:{topic}:{partition}:{offset}"
