import asyncio
import hmac
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from fastapi import Depends, FastAPI, Header, HTTPException
from fastembed import TextEmbedding
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from qdrant_client import AsyncQdrantClient
from qdrant_client import models as q


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[3] / ".env", extra="ignore")
    service_token: str = ""
    qdrant_url: str = "http://127.0.0.1:6338"
    qdrant_prefix: str = "ac_"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512


settings = Settings()
client = AsyncQdrantClient(url=settings.qdrant_url)
embedder = None
embedding_error = False
embedding_lock = asyncio.Lock()
job_locks = {}


async def warmup():
    global embedder, embedding_error
    try:
        embedder = await asyncio.to_thread(TextEmbedding, model_name=settings.embedding_model)
    except Exception:
        embedding_error = True


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(warmup())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    await client.close()


async def authorize(authorization: str = Header(default="")):
    if not settings.service_token or not hmac.compare_digest(
        authorization, "Bearer " + settings.service_token
    ):
        raise HTTPException(401, "Unauthorized")


app = FastAPI(title="AI Character RAG", version="0.1.0", lifespan=lifespan, dependencies=[Depends(authorize)])


class Scope(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    character_id: str = Field(min_length=1, max_length=100)


class MemoryScope(Scope):
    conversation_id: str = Field(min_length=1, max_length=100)


class Publish(Scope):
    text: str = Field(max_length=100000)
    version: str = Field(min_length=1, max_length=100)


class Context(MemoryScope):
    query: str = Field(min_length=1, max_length=12000)
    background_version: str | None = None
    memory_enabled: bool = True


class Ingest(MemoryScope):
    job_id: str
    source_message_ids: list[str]
    facts: list[str] = Field(max_length=5)
    phase_id: str | None = None


def collection(kind):
    return settings.qdrant_prefix + kind


def filters(values):
    return q.Filter(
        must=[
            q.FieldCondition(key=k, match=q.MatchValue(value=v)) for k, v in values.items() if v is not None
        ]
    )


async def vectors(texts):
    if embedder is None:
        raise HTTPException(503, "Embedding model is loading or unavailable; check RAG health")
    async with embedding_lock:
        result = await asyncio.to_thread(lambda: [x.tolist() for x in embedder.embed(texts)])
    if any(len(x) != settings.embedding_dim for x in result):
        raise HTTPException(503, "Embedding dimensions do not match database; run setup check")
    return result


@app.get("/health")
async def health():
    await client.get_collections()
    return {"ready": embedder is not None, "embedding_error": embedding_error, "memory_configured": True}


@app.post("/background/publish")
async def publish(body: Publish):
    chunks = [body.text[i : i + 700] for i in range(0, len(body.text), 600) if body.text[i : i + 700].strip()]
    if chunks:
        embeddings = await vectors(chunks)
        points = [
            q.PointStruct(
                id=str(uuid5(NAMESPACE_URL, f"{body.user_id}:{body.character_id}:{body.version}:{i}")),
                vector=vector,
                payload={**body.model_dump(exclude={"text"}), "text": chunk},
            )
            for i, (chunk, vector) in enumerate(zip(chunks, embeddings))
        ]
        await client.upsert(collection("background"), points=points, wait=True)
    return {"chunks": len(chunks)}


@app.post("/context")
async def context(body: Context):
    if not body.background_version and not body.memory_enabled:
        return {"background": [], "memory": []}
    vector = (await vectors([body.query]))[0]
    scope = body.model_dump(include={"user_id", "character_id"})
    result = {"background": [], "memory": []}
    if body.background_version:
        found = await client.query_points(
            collection("background"),
            query=vector,
            query_filter=filters({**scope, "version": body.background_version}),
            limit=4,
        )
        result["background"] = [p.payload["text"] for p in found.points]
    if body.memory_enabled:
        found = await client.query_points(
            collection("memory"),
            query=vector,
            query_filter=filters({**scope, "conversation_id": body.conversation_id, "type": "memory"}),
            limit=6,
        )
        result["memory"] = [p.payload["text"] for p in found.points]
    return result


@app.post("/memory/ingest")
async def ingest(body: Ingest):
    identity = f"{body.user_id}:{body.character_id}:{body.conversation_id}:{body.job_id}"
    receipt_id = str(uuid5(NAMESPACE_URL, identity + ":receipt"))
    async with job_locks.setdefault(identity, asyncio.Lock()):
        previous = await client.retrieve(collection("memory"), ids=[receipt_id])
        if previous:
            return {"facts": previous[0].payload["facts"], "replayed": True}
        facts = [text[:500] for text in body.facts if text.strip()]
        embeddings = await vectors(facts) if facts else []
        scope = body.model_dump(exclude={"facts"})
        points = [
            q.PointStruct(
                id=str(
                    uuid5(
                        NAMESPACE_URL,
                        f"{body.user_id}:{body.character_id}:{body.conversation_id}:fact:{fact.strip().casefold()}",
                    )
                ),
                vector=vector,
                payload={**scope, "text": fact, "type": "memory"},
            )
            for i, (fact, vector) in enumerate(zip(facts, embeddings))
        ]
        points.append(
            q.PointStruct(
                id=receipt_id,
                vector=[1.0] + [0.0] * (settings.embedding_dim - 1),
                payload={**scope, "type": "receipt", "facts": len(facts)},
            )
        )
        await client.upsert(collection("memory"), points=points, wait=True)
        return {"facts": len(facts)}


@app.post("/memory/list")
async def list_memory(body: MemoryScope):
    points, cursor = await client.scroll(
        collection("memory"), scroll_filter=filters({**body.model_dump(), "type": "memory"}), limit=100
    )
    return {"facts": [p.payload for p in points], "has_more": cursor is not None}


@app.post("/memory/delete")
async def delete_memory(body: MemoryScope):
    await client.delete(
        collection("memory"), points_selector=q.FilterSelector(filter=filters(body.model_dump())), wait=True
    )
    return {"deleted": True}


@app.post("/background/delete")
async def delete_background(body: Scope):
    await client.delete(
        collection("background"),
        points_selector=q.FilterSelector(filter=filters(body.model_dump())),
        wait=True,
    )
    return {"deleted": True}
