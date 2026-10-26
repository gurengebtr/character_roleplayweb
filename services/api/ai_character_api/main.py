import asyncio
import hashlib
from contextlib import asynccontextmanager, suppress
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from . import chat, oauth, providers, worker
from .auth import service_auth, user_auth, verify_password
from .config import settings
from .credentials import store
from .database import db, public
from .models import CharacterInput, ConversationInput, ConversationState, EndpointInput, LoginInput, TurnInput


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(worker.run()) if settings.worker_enabled else None
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="AI Character API", version="0.1.0", lifespan=lifespan)


@app.get("/health", dependencies=[Depends(service_auth)])
async def health():
    await db.command("ping")
    try:
        status = await chat.rag("GET", "/health", timeout=3)
    except httpx.HTTPError:
        status = {"ready": False, "detail": "RAG unavailable"}
    return {"mongo": True, "rag": status}


@app.post("/auth/login", dependencies=[Depends(service_auth)])
async def login(body: LoginInput):
    user = await db.users.find_one({"username": body.username})
    if not user or not await asyncio.to_thread(verify_password, body.password, user["password_hash"]):
        await asyncio.sleep(0.3)
        raise HTTPException(401, "Invalid credentials")
    return public(user)


@app.get("/characters")
async def characters(user=Depends(user_auth)):
    return [public(c) async for c in db.characters.find({"owner_id": user}).sort("updated_at", -1)]


@app.post("/characters", status_code=201)
async def create_character(body: CharacterInput, user=Depends(user_auth)):
    doc = {
        **body.model_dump(),
        "character_id": uuid4().hex,
        "owner_id": user,
        "revision": 1,
        "created_at": chat.now(),
        "updated_at": chat.now(),
        "published_hash": None,
    }
    await db.characters.insert_one(doc)
    return public(doc)


@app.put("/characters/{identity}")
async def update_character(identity: str, body: CharacterInput, user=Depends(user_auth)):
    async with chat.serial("character:" + identity):
        await chat.owned("characters", identity, user)
        # Old conversations must continue to resolve their chosen phase.
        used = await db.conversations.distinct("state.phase_id", {"character_id": identity})
        if set(filter(None, used)) - {p.id for p in body.phases}:
            raise HTTPException(409, "A phase is used by existing chats; switch those chats first")
        await db.characters.update_one(
            {"character_id": identity},
            {"$set": {**body.model_dump(), "updated_at": chat.now()}, "$inc": {"revision": 1}},
        )
        return public(await chat.owned("characters", identity, user))


@app.delete("/characters/{identity}")
async def delete_character(identity: str, user=Depends(user_auth)):
    async with chat.serial("character:" + identity):
        await chat.owned("characters", identity, user)
        if await db.conversations.find_one({"character_id": identity}):
            raise HTTPException(409, "Delete this character's conversations first")
        try:
            await chat.rag("POST", "/background/delete", {"user_id": user, "character_id": identity})
        except httpx.HTTPError:
            raise HTTPException(503, "RAG unavailable; character was not deleted") from None
        await db.characters.delete_one({"character_id": identity})
        return {"deleted": True}


@app.post("/characters/{identity}/publish")
async def publish(identity: str, user=Depends(user_auth)):
    async with chat.serial("character:" + identity):
        character = await chat.owned("characters", identity, user)
        version = hashlib.sha256(character["background"].encode()).hexdigest()
        try:
            result = await chat.rag(
                "POST",
                "/background/publish",
                {
                    "user_id": user,
                    "character_id": identity,
                    "text": character["background"],
                    "version": version,
                },
                timeout=120,
            )
        except httpx.HTTPError:
            raise HTTPException(
                503, "Background publishing failed; previous published version remains active"
            ) from None
        await db.characters.update_one(
            {"character_id": identity},
            {
                "$set": {
                    "published_hash": version,
                    "published_background": character["background"],
                    "published_at": chat.now(),
                }
            },
        )
        return {**result, "published_hash": version}


@app.get("/conversations")
async def conversations(user=Depends(user_auth)):
    return [public(c) async for c in db.conversations.find({"user_id": user}).sort("updated_at", -1)]


@app.post("/conversations", status_code=201)
async def create_conversation(body: ConversationInput, user=Depends(user_auth)):
    async with chat.serial("character:" + body.character_id):
        character = await chat.owned("characters", body.character_id, user)
        doc = {
            "conversation_id": uuid4().hex,
            "user_id": user,
            "character_id": body.character_id,
            "title": body.title,
            "state": {"phase_id": character["phases"][0]["id"] if character["phases"] else None},
            "memory_note": "",
            "revision": 1,
            "created_at": chat.now(),
            "updated_at": chat.now(),
        }
        await db.conversations.insert_one(doc)
        if character["opening_message"]:
            await db.messages.insert_one(
                {
                    "message_id": uuid4().hex,
                    "conversation_id": doc["conversation_id"],
                    "role": "assistant",
                    "content": character["opening_message"],
                    "phase_id": doc["state"]["phase_id"],
                    "created_at": chat.now(),
                    "origin": "opening",
                    "position": 0,
                }
            )
        return public(doc)


@app.get("/conversations/{identity}/messages")
async def messages(
    identity: str,
    before: int | None = Query(None, ge=0),
    limit: int = Query(100, ge=1, le=200),
    user=Depends(user_auth),
):
    await chat.owned("conversations", identity, user)
    query = {"conversation_id": identity}
    if before is not None:
        query["position"] = {"$lt": before}
    rows = await db.messages.find(query).sort("position", -1).limit(limit + 1).to_list()
    page = rows[:limit]
    return {
        "items": [public(x) for x in reversed(page)],
        "next_cursor": str(page[-1]["position"]) if len(rows) > limit else None,
    }


@app.patch("/conversations/{identity}")
async def update_state(identity: str, body: ConversationState, user=Depends(user_auth)):
    async with chat.serial(identity):
        conv = await chat.owned("conversations", identity, user)
        if conv.get("deleting"):
            raise HTTPException(409, "Conversation deletion in progress")
        character = await chat.owned("characters", conv["character_id"], user)
        if body.phase_id and body.phase_id not in {p["id"] for p in character["phases"]}:
            raise HTTPException(400, "Unknown phase")
        result = await db.conversations.update_one(
            {"conversation_id": identity, "revision": body.revision},
            {
                "$set": {
                    "state.phase_id": body.phase_id,
                    "memory_note": body.memory_note,
                    "updated_at": chat.now(),
                },
                "$inc": {"revision": 1},
            },
        )
        if not result.modified_count:
            raise HTTPException(409, "Conversation changed; refresh and try again")
        return public(await chat.owned("conversations", identity, user))


@app.post("/conversations/{identity}/messages")
async def send_message(identity: str, body: TurnInput, user=Depends(user_auth)):
    return await chat.send(user, identity, body.content, body.request_id)


@app.delete("/conversations/{identity}")
async def remove_conversation(identity: str, user=Depends(user_auth)):
    return await chat.delete_conversation(user, identity)


@app.get("/conversations/{identity}/memory")
async def memory(identity: str, user=Depends(user_auth)):
    conv = await chat.owned("conversations", identity, user)
    jobs = (
        await db.memory_jobs.find({"conversation_id": identity}, {"_id": 0, "messages": 0})
        .sort("created_at", -1)
        .limit(20)
        .to_list()
    )
    try:
        result = await chat.rag(
            "POST",
            "/memory/list",
            {"user_id": user, "character_id": conv["character_id"], "conversation_id": identity},
        )
    except httpx.HTTPError:
        result = {"facts": [], "unavailable": True}
    return {**result, "jobs": jobs}


@app.post("/conversations/{identity}/memory/retry")
async def retry_memory(identity: str, user=Depends(user_auth)):
    conv = await chat.owned("conversations", identity, user)
    if conv.get("deleting"):
        raise HTTPException(409, "Conversation deletion in progress")
    await db.memory_jobs.update_many(
        {"conversation_id": identity, "status": {"$in": ["failed", "dead"]}},
        {"$set": {"status": "pending", "attempts": 0, "next_attempt_at": chat.now()}},
    )
    return {"queued": True}


@app.get("/settings")
async def get_settings(user=Depends(user_auth)):
    data = store.load(user)
    endpoint = data.get("endpoint", {})
    return {
        "endpoint": {k: endpoint.get(k, "") for k in ["base_url", "model"]},
        "api_key_configured": bool(endpoint.get("api_key")),
        "active_account": data.get("active"),
        "accounts": [
            {"id": key, "email": a["email"], "connected": bool(a.get("access_token"))}
            for key, a in data["accounts"].items()
        ],
    }


@app.put("/settings/endpoint")
async def save_endpoint(body: EndpointInput, user=Depends(user_auth)):
    parsed = urlparse(body.base_url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(400, "Enter a valid http(s) base URL without credentials, query or fragment")
    async with oauth.lock(user):
        data = store.load(user)
        endpoint = body.model_dump(exclude_none=True)
        if body.api_key is None:
            endpoint["api_key"] = data.get("endpoint", {}).get("api_key", "")
        data["endpoint"] = endpoint
        store.save(user, data)
    return {"saved": True}


@app.post("/providers/chatgpt/connect")
async def connect(account: str | None = None, user=Depends(user_auth)):
    return {"url": oauth.start(user, account)}


@app.post("/providers/chatgpt/select/{account}")
async def select(account: str, user=Depends(user_auth)):
    async with oauth.lock(user):
        data = store.load(user)
        if not data["accounts"].get(account, {}).get("access_token"):
            raise HTTPException(409, "Reconnect this ChatGPT account first")
        data["active"] = account
        store.save(user, data)
    return {"selected": True}


@app.post("/providers/chatgpt/disconnect/{account}")
async def disconnect(account: str, user=Depends(user_auth)):
    return {"revocation_confirmed": await oauth.disconnect(user, account)}


@app.get("/providers/chatgpt/models")
async def models(user=Depends(user_auth)):
    return await providers.catalog(user)


@app.get("/auth/callback")
async def callback(
    state: str = "", code: str | None = None, client_id: str | None = None, error: str | None = None
):
    try:
        await oauth.callback(state, code, client_id, error)
    except (HTTPException, httpx.HTTPError, ValueError, KeyError):
        return HTMLResponse(
            "<h1>ChatGPT connection failed</h1><p>Permission was declined, the attempt expired, or verification failed. Return to Settings and start again.</p>",
            status_code=400,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )
    return RedirectResponse(
        settings.web_url + "/?connected=1",
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
