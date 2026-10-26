from pymongo import AsyncMongoClient

from .config import settings

client = AsyncMongoClient(settings.mongo_uri, serverSelectionTimeoutMS=3000)
db = client[settings.mongo_db]


def public(doc):
    if doc is None:
        return None
    return {k: v for k, v in doc.items() if k not in {"_id", "pending_commit", "password_hash"}}
