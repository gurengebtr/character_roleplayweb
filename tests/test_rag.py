import pytest
from ai_character_rag import main as rag
from qdrant_client import AsyncQdrantClient
from qdrant_client import models as q


@pytest.mark.asyncio
async def test_background_version_memory_scope_idempotence_and_delete(monkeypatch):
    client = AsyncQdrantClient(":memory:")
    monkeypatch.setattr(rag, "client", client)
    monkeypatch.setattr(rag.settings, "embedding_dim", 3)
    for kind in ["background", "memory"]:
        await client.create_collection(
            rag.collection(kind), vectors_config=q.VectorParams(size=3, distance=q.Distance.COSINE)
        )

    async def vectors(texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(rag, "vectors", vectors)
    scope = {"user_id": "u", "character_id": "c"}
    await rag.publish(rag.Publish(**scope, text="舊背景", version="v1"))
    await rag.publish(rag.Publish(**scope, text="新背景", version="v2"))
    body = rag.Ingest(
        **scope,
        conversation_id="one",
        job_id="job",
        facts=["喜歡茶"],
        source_message_ids=["m"],
        phase_id=None,
    )
    assert (await rag.ingest(body))["facts"] == 1
    assert (await rag.ingest(body))["replayed"]
    assert len((await rag.list_memory(rag.MemoryScope(**scope, conversation_id="one")))["facts"]) == 1
    context = await rag.context(
        rag.Context(**scope, conversation_id="one", query="茶", background_version="v1")
    )
    assert context == {"background": ["舊背景"], "memory": ["喜歡茶"]}
    other = await rag.context(
        rag.Context(**scope, conversation_id="two", query="茶", background_version="v2")
    )
    assert other == {"background": ["新背景"], "memory": []}
    stranger = await rag.context(
        rag.Context(
            user_id="other", character_id="c", conversation_id="one", query="茶", background_version="v1"
        )
    )
    assert stranger == {"background": [], "memory": []}
    await rag.delete_memory(rag.MemoryScope(**scope, conversation_id="one"))
    assert (await client.count(rag.collection("memory"))).count == 0
    await client.close()
