import asyncio
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from ai_character_api import chat, main, oauth, providers, worker
from ai_character_api.credentials import CredentialStore
from cryptography.fernet import Fernet
from pymongo import AsyncMongoClient

from scripts.schema import INDEXES


@pytest_asyncio.fixture
async def environment(monkeypatch, tmp_path):
    client = AsyncMongoClient("mongodb://127.0.0.1:27028", serverSelectionTimeoutMS=2000)
    name = "ac_test_" + uuid4().hex
    db = client[name]
    for collection, indexes in INDEXES.items():
        for index, keys, unique in indexes:
            await db[collection].create_index(keys, name=index, unique=unique)
    for module in [main, chat, worker]:
        monkeypatch.setattr(module, "db", db)
    vault = CredentialStore(tmp_path, Fernet.generate_key().decode())
    for module in [main, oauth, providers]:
        monkeypatch.setattr(module, "store", vault)
    calls = []

    async def model(user, character, prompt, history):
        calls.append(prompt)
        return '["喜歡熱茶"]' if prompt.startswith("Extract") else "你好，旅人。"

    async def rag(method, path, payload=None, timeout=15):
        if path == "/context":
            return {"background": ["來自港口的鍊金術師"], "memory": []}
        return {"facts": 1}

    monkeypatch.setattr(providers, "generate", model)
    monkeypatch.setattr(chat, "rag", rag)
    monkeypatch.setattr(worker, "rag", rag)
    headers = {"Authorization": "Bearer " + main.settings.service_token, "X-User-ID": "test-owner"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test", headers=headers
    ) as http:
        yield http, db, calls
    await client.drop_database(name)
    await client.close()


async def character_and_chat(http):
    response = await http.post(
        "/characters",
        json={
            "name": "莉亞",
            "system_prompt": "你是莉亞",
            "provider": "endpoint",
            "phases": [
                {"id": "new", "name": "初識", "prompt": "禮貌地回應"},
                {"id": "close", "name": "熟悉", "prompt": "親切地回應"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    character = response.json()
    conv = (await http.post("/conversations", json={"character_id": character["character_id"]})).json()
    return character, conv


@pytest.mark.asyncio
async def test_turn_replay_phase_memory_and_isolation(environment):
    http, db, calls = environment
    character, conv = await character_and_chat(http)
    path = "/conversations/" + conv["conversation_id"]
    changed = await http.patch(path, json={"phase_id": "close", "memory_note": "一起旅行", "revision": 1})
    assert changed.status_code == 200
    assert (
        await http.patch(path, json={"phase_id": "new", "memory_note": "", "revision": 1})
    ).status_code == 409
    body = {"content": "我喜歡熱茶", "request_id": "test-request-001"}
    results = await asyncio.gather(
        http.post(path + "/messages", json=body), http.post(path + "/messages", json=body)
    )
    assert all(r.status_code == 200 for r in results)
    assert sum(r.json()["replayed"] for r in results) == 1
    assert len(calls) == 1 and "親切" in calls[0] and "一起旅行" in calls[0]
    assert await db.messages.count_documents({}) == 2
    assert await db.memory_jobs.count_documents({}) == 1
    assert (await http.post(path + "/messages", json={**body, "content": "different"})).status_code == 409
    assert (await http.get(path + "/messages", headers={"X-User-ID": "other"})).status_code == 404
    await worker.tick()
    job = await db.memory_jobs.find_one({})
    assert job["status"] == "complete" and "messages" not in job
    assert job["extracted_facts"] == ["喜歡熱茶"]
    assert (await http.delete("/characters/" + character["character_id"])).status_code == 409
    assert (await http.delete(path)).status_code == 200
    assert await db.messages.count_documents({}) == 0
    assert await db.memory_jobs.count_documents({}) == 0
    assert (await http.delete("/characters/" + character["character_id"])).status_code == 200


@pytest.mark.asyncio
async def test_model_failure_leaves_no_half_turn(environment, monkeypatch):
    http, db, _ = environment
    _, conv = await character_and_chat(http)

    async def fail(*args):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(providers, "generate", fail)
    response = await http.post(
        f"/conversations/{conv['conversation_id']}/messages",
        json={"content": "hello", "request_id": "failure-001"},
    )
    assert response.status_code == 502
    assert await db.messages.count_documents({}) == 0
    assert await db.memory_jobs.count_documents({}) == 0


@pytest.mark.asyncio
async def test_commit_journal_recovers_after_partial_write(environment, monkeypatch):
    http, db, _ = environment
    _, conv = await character_and_chat(http)
    original = chat.commit_pending

    async def partial(row):
        if row.get("pending_commit"):
            message = row["pending_commit"]["messages"][0]
            await db.messages.insert_one(message.copy())
            raise RuntimeError("simulated process crash")

    monkeypatch.setattr(chat, "commit_pending", partial)
    path = f"/conversations/{conv['conversation_id']}/messages"
    body = {"content": "你好", "request_id": "crash-001"}
    with pytest.raises(RuntimeError):
        await http.post(path, json=body)
    monkeypatch.setattr(chat, "commit_pending", original)
    response = await http.post(path, json=body)
    assert response.status_code == 200 and response.json()["replayed"]
    assert await db.messages.count_documents({}) == 2
    assert await db.memory_jobs.count_documents({}) == 1
    assert "pending_commit" not in await db.conversations.find_one({})


@pytest.mark.asyncio
async def test_service_auth_and_phase_removal(environment):
    http, _, _ = environment
    assert (await http.get("/characters", headers={"Authorization": "Bearer bad"})).status_code == 401
    character, _ = await character_and_chat(http)
    body = {
        k: character[k]
        for k in [
            "name",
            "system_prompt",
            "opening_message",
            "background",
            "memory_enabled",
            "provider",
            "model",
        ]
    }
    body["phases"] = []
    assert (await http.put("/characters/" + character["character_id"], json=body)).status_code == 409


@pytest.mark.asyncio
async def test_delete_tombstone_retries_and_blocks_chat(environment, monkeypatch):
    http, db, _ = environment
    _, conv = await character_and_chat(http)
    original = chat.rag

    async def fail(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(chat, "rag", fail)
    path = "/conversations/" + conv["conversation_id"]
    assert (await http.delete(path)).status_code == 503
    assert (
        await http.post(path + "/messages", json={"content": "test", "request_id": "tombstone-001"})
    ).status_code == 409
    monkeypatch.setattr(chat, "rag", original)
    assert (await http.delete(path)).status_code == 200
    assert await db.conversations.count_documents({}) == 0


@pytest.mark.asyncio
async def test_memory_extraction_does_not_lock_chat_or_resurrect_deleted_memory(environment, monkeypatch):
    http, db, _ = environment
    _, conv = await character_and_chat(http)
    path = "/conversations/" + conv["conversation_id"]
    await http.post(path + "/messages", json={"content": "I like tea", "request_id": "memory-race-001"})
    extracting, release = asyncio.Event(), asyncio.Event()
    indexed = []

    async def slow(*args):
        extracting.set()
        await release.wait()
        return '["tea"]'

    async def index(*args, **kwargs):
        indexed.append(args)
        return {"facts": 1}

    monkeypatch.setattr(providers, "generate", slow)
    monkeypatch.setattr(worker, "rag", index)
    task = asyncio.create_task(worker.tick())
    try:
        await asyncio.wait_for(extracting.wait(), timeout=2)
        result = await asyncio.wait_for(http.delete(path), timeout=2)
        assert result.status_code == 200
        release.set()
        await task
        assert not indexed
        assert await db.memory_jobs.count_documents({}) == 0
    finally:
        release.set()
        await task


@pytest.mark.asyncio
async def test_order_and_cursor_are_stable_after_opening(environment):
    http, _, _ = environment
    created = (
        await http.post(
            "/characters", json={"name": "Test", "system_prompt": "test", "opening_message": "Opening"}
        )
    ).json()
    conv = (await http.post("/conversations", json={"character_id": created["character_id"]})).json()
    path = "/conversations/" + conv["conversation_id"] + "/messages"
    await http.post(path, json={"content": "First user message", "request_id": "order-001"})
    page = (await http.get(path + "?limit=2")).json()
    assert [m["role"] for m in page["items"]] == ["user", "assistant"]
    assert page["next_cursor"] == "1"
    older = (await http.get(path + "?before=1&limit=2")).json()
    assert [m["content"] for m in older["items"]] == ["Opening"]
    assert older["next_cursor"] is None
