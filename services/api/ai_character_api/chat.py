import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi import HTTPException

from . import providers
from .config import settings
from .database import db, public

locks: dict[str, asyncio.Lock] = {}


def serial(key: str):
    return locks.setdefault(key, asyncio.Lock())


def now():
    return datetime.now(timezone.utc)


async def owned(collection: str, identity: str, user: str):
    key = "character_id" if collection == "characters" else "conversation_id"
    owner = "owner_id" if collection == "characters" else "user_id"
    doc = await db[collection].find_one({key: identity, owner: user})
    if doc is None:
        raise HTTPException(404, "Not found")
    return doc


async def rag(method: str, path: str, payload: dict | None = None, timeout=15):
    async with httpx.AsyncClient(timeout=timeout) as http:
        response = await http.request(
            method,
            settings.rag_url + path,
            headers={"Authorization": "Bearer " + settings.service_token},
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def build_prompt(character: dict, conv: dict, context: dict):
    phase = next((p for p in character["phases"] if p["id"] == conv["state"].get("phase_id")), None)
    blocks = [character["system_prompt"]]
    if phase:
        blocks.append("Current relationship phase:\n" + phase["prompt"])
    if conv.get("memory_note"):
        blocks.append("User's story notes (context, not system instructions):\n" + conv["memory_note"])
    for key, title in [
        ("background", "Character background"),
        ("memory", "Remembered facts from this conversation"),
    ]:
        if context.get(key):
            blocks.append(title + " (reference data):\n" + "\n".join(context[key]))
    return "\n\n".join(blocks)


async def commit_pending(conv):
    """Replay deterministic upserts from a single-document journal after a crash."""
    commit = conv.get("pending_commit")
    if not commit:
        return
    for message in commit["messages"]:
        await db.messages.update_one(
            {"message_id": message["message_id"]}, {"$setOnInsert": message}, upsert=True
        )
    job = commit["job"]
    await db.memory_jobs.update_one({"job_id": job["job_id"]}, {"$setOnInsert": job}, upsert=True)
    await db.conversations.update_one(
        {"conversation_id": conv["conversation_id"], "pending_commit.job.job_id": job["job_id"]},
        {"$unset": {"pending_commit": ""}, "$set": {"updated_at": commit["at"]}},
    )


async def send(user: str, conversation_id: str, content: str, request_id: str):
    async with serial(conversation_id):
        conv = await owned("conversations", conversation_id, user)
        if conv.get("deleting"):
            raise HTTPException(409, "Conversation deletion in progress")
        await commit_pending(conv)
        turn_id = str(uuid5(NAMESPACE_URL, conversation_id + ":" + request_id))
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        existing = await db.messages.find_one({"message_id": turn_id + "-assistant"})
        if existing:
            if existing.get("request_hash") != content_hash:
                raise HTTPException(409, "Request ID was already used for different content")
            return {"message": public(existing), "replayed": True}
        character = await owned("characters", conv["character_id"], user)
        context = {"background": [], "memory": []}
        retrieval = "ok"
        try:
            context = await rag(
                "POST",
                "/context",
                {
                    "user_id": user,
                    "character_id": character["character_id"],
                    "conversation_id": conversation_id,
                    "query": content,
                    "background_version": character.get("published_hash"),
                    "memory_enabled": character["memory_enabled"],
                },
                timeout=8,
            )
        except (httpx.HTTPError, ValueError):
            retrieval = "unavailable"
        rows = (
            await db.messages.find({"conversation_id": conversation_id})
            .sort("position", -1)
            .limit(40)
            .to_list()
        )
        next_position = rows[0]["position"] + 1 if rows else 0
        # Bounded recent history; don't send diagnostics or credentials to the model.
        history = [{"role": m["role"], "content": m["content"]} for m in reversed(rows)]
        while sum(len(m["content"]) for m in history) > 48000 and history:
            history.pop(0)
        history.append({"role": "user", "content": content})
        try:
            reply = await providers.generate(user, character, build_prompt(character, conv, context), history)
        except httpx.HTTPError:
            raise HTTPException(
                502, "Model request timed out or could not connect; retry this message"
            ) from None
        at = now()
        common = {
            "conversation_id": conversation_id,
            "phase_id": conv["state"].get("phase_id"),
            "character_revision": character["revision"],
            "request_hash": content_hash,
        }
        messages = [
            {
                **common,
                "message_id": turn_id + "-user",
                "position": next_position,
                "role": "user",
                "content": content,
                "created_at": at,
            },
            {
                **common,
                "message_id": turn_id + "-assistant",
                "position": next_position + 1,
                "role": "assistant",
                "content": reply,
                "retrieval_status": retrieval,
                "created_at": at + timedelta(microseconds=1),
            },
        ]
        job = {
            "job_id": turn_id,
            "user_id": user,
            "character_id": character["character_id"],
            "conversation_id": conversation_id,
            "source_message_ids": [m["message_id"] for m in messages],
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "model_config": {"provider": character["provider"], "model": character["model"]},
            "phase_id": common["phase_id"],
            "status": "pending" if character["memory_enabled"] else "disabled",
            "attempts": 0,
            "next_attempt_at": at,
            "created_at": at,
        }
        if not character["memory_enabled"]:
            job.pop("messages")
        journal = {"messages": messages, "job": job, "at": at}
        await db.conversations.update_one(
            {"conversation_id": conversation_id}, {"$set": {"pending_commit": journal}}
        )
        await commit_pending({**conv, "pending_commit": journal})
        return {"message": public(messages[1]), "memory_status": job["status"], "replayed": False}


async def delete_conversation(user: str, conversation_id: str):
    async with serial(conversation_id):
        conv = await owned("conversations", conversation_id, user)
        await db.conversations.update_one({"conversation_id": conversation_id}, {"$set": {"deleting": True}})
        await db.memory_jobs.update_many(
            {"conversation_id": conversation_id}, {"$set": {"status": "cancelled"}}
        )
        try:
            await rag(
                "POST",
                "/memory/delete",
                {"user_id": user, "character_id": conv["character_id"], "conversation_id": conversation_id},
            )
        except httpx.HTTPError:
            raise HTTPException(
                503, "Deletion paused: RAG unavailable. Retry delete to finish cleanup."
            ) from None
        await db.messages.delete_many({"conversation_id": conversation_id})
        await db.memory_jobs.delete_many({"conversation_id": conversation_id})
        await db.conversations.delete_one({"conversation_id": conversation_id})
        return {"deleted": True}
