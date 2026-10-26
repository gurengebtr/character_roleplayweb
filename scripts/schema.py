"""Inspect first, apply only additive changes after all compatibility checks pass."""

from qdrant_client import models

INDEXES = {
    "characters": [
        ("character_id", [("character_id", 1)], True),
        ("owner", [("owner_id", 1), ("updated_at", -1)], False),
    ],
    "conversations": [
        ("conversation_id", [("conversation_id", 1)], True),
        ("owner", [("user_id", 1), ("updated_at", -1)], False),
    ],
    "messages": [
        ("message_id", [("message_id", 1)], True),
        ("message_order", [("conversation_id", 1), ("position", 1)], True),
        ("history", [("conversation_id", 1), ("created_at", 1), ("_id", 1)], False),
    ],
    "memory_jobs": [
        ("job_id", [("job_id", 1)], True),
        ("due", [("status", 1), ("next_attempt_at", 1)], False),
    ],
    "users": [("username", [("username", 1)], True)],
    "settings": [("key", [("key", 1)], True)],
}


def inspect_schema(db, qdrant, prefix, dimension):
    additions, conflicts, notices = [], [], []
    version = db.settings.find_one({"key": "schema"})
    if version and version.get("version") != 1:
        conflicts.append("Mongo schema version differs; explicit migration required")
    for collection, indexes in INDEXES.items():
        existing = db[collection].index_information()
        for name, keys, unique in indexes:
            current = existing.get(name)
            if current and (current["key"] != keys or bool(current.get("unique")) != unique):
                conflicts.append(f"Mongo {collection}.{name} index differs")
            elif not current:
                additions.append(
                    (
                        f"Mongo index {collection}.{name}",
                        lambda c=collection, k=keys, n=name, u=unique: db[c].create_index(
                            k, name=n, unique=u
                        ),
                    )
                )
    for collection in set(db.list_collection_names()) - set(INDEXES):
        notices.append(f"unknown Mongo collection {collection}; left unchanged")
    expected = {prefix + "background", prefix + "memory"}
    for name in sorted(expected):
        exists = qdrant.collection_exists(name)
        if exists:
            info = qdrant.get_collection(name)
            vector = info.config.params.vectors
            if (
                not isinstance(vector, models.VectorParams)
                or vector.size != dimension
                or vector.distance != models.Distance.COSINE
            ):
                conflicts.append(f"Qdrant {name} vector schema differs; explicit reindex required")
                continue
            payload = info.payload_schema
        else:
            payload = {}
            additions.append(
                (
                    f"Qdrant collection {name}",
                    lambda n=name: qdrant.create_collection(
                        n, vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE)
                    ),
                )
            )
        for field in ["user_id", "character_id", "conversation_id", "version", "job_id", "type"]:
            current = payload.get(field)
            if current and current.data_type != models.PayloadSchemaType.KEYWORD:
                conflicts.append(f"Qdrant {name}.{field} payload type differs")
            elif not current:
                additions.append(
                    (
                        f"Qdrant index {name}.{field}",
                        lambda n=name, f=field: qdrant.create_payload_index(
                            n, f, models.PayloadSchemaType.KEYWORD, wait=True
                        ),
                    )
                )
    for name in {c.name for c in qdrant.get_collections().collections} - expected:
        notices.append(f"unknown Qdrant collection {name}; left unchanged")
    return additions, conflicts, notices
