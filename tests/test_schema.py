from uuid import uuid4

from pymongo import MongoClient
from qdrant_client import QdrantClient, models

from scripts.schema import inspect_schema


def test_schema_plan_is_readonly_and_detects_incompatible_vector():
    mongo = MongoClient("mongodb://127.0.0.1:27028", serverSelectionTimeoutMS=2000)
    name = "ac_test_" + uuid4().hex
    db = mongo[name]
    qdrant = QdrantClient(":memory:")
    try:
        qdrant.create_collection(
            "ac_background", vectors_config=models.VectorParams(size=5, distance=models.Distance.COSINE)
        )
        additions, conflicts, _ = inspect_schema(db, qdrant, "ac_", 3)
        assert additions and conflicts
        assert not db.list_collection_names()
        assert not qdrant.collection_exists("ac_memory")
        qdrant.delete_collection("ac_background")
        additions, conflicts, _ = inspect_schema(db, qdrant, "ac_", 3)
        assert not conflicts
        # Local in-memory Qdrant doesn't persist payload indexes, so verify Mongo
        # compatibility separately after applying the complete additive plan.
        for _, apply in additions:
            apply()
        additions, conflicts, _ = inspect_schema(db, qdrant, "ac_", 3)
        assert not conflicts and all(label.startswith("Qdrant index") for label, _ in additions)
        db.characters.drop_index("character_id")
        db.characters.create_index("character_id", name="character_id", unique=False)
        _, conflicts, _ = inspect_schema(db, qdrant, "ac_", 3)
        assert any("characters.character_id" in x for x in conflicts)
    finally:
        mongo.drop_database(name)
        mongo.close()
        qdrant.close()
