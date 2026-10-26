import json

import httpx
from fastapi import HTTPException

from . import oauth
from .credentials import store


async def catalog(user: str) -> list[dict]:
    token = await oauth.access_token(user)
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.get(oauth.RESOURCE + "/models", headers={"Authorization": "Bearer " + token})
    if response.status_code != 200:
        raise HTTPException(502, f"ChatGPT model list failed ({response.status_code})")
    return [
        {"slug": m["slug"], "display_name": m.get("display_name", m["slug"])}
        for m in response.json().get("models", [])
        if m.get("visibility") == "list"
    ]


async def generate(user: str, character: dict, instructions: str, history: list[dict]) -> str:
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10)) as http:
        if character["provider"] == "chatgpt":
            token = await oauth.access_token(user)
            if not character["model"]:
                raise HTTPException(409, "Choose an available ChatGPT model in the character editor")
            text = []
            completed = False
            async with http.stream(
                "POST",
                oauth.RESOURCE + "/responses",
                headers={"Authorization": "Bearer " + token},
                json={
                    "model": character["model"],
                    "instructions": instructions,
                    "input": history,
                    "store": False,
                    "stream": True,
                },
            ) as response:
                if response.status_code != 200:
                    raise HTTPException(
                        502, f"ChatGPT inference failed ({response.status_code}); check connection and usage"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        continue
                    event = json.loads(raw)
                    kind = event.get("type")
                    if kind == "response.output_text.delta":
                        text.append(event.get("delta", ""))
                        if sum(map(len, text)) > 64000:
                            raise HTTPException(502, "Model reply exceeds MVP message size limit")
                    elif kind == "response.completed":
                        completed = True
                    elif kind in {"error", "response.failed", "response.incomplete"}:
                        raise HTTPException(502, "ChatGPT response failed or incomplete; no reply saved")
            if not completed or not "".join(text).strip():
                raise HTTPException(502, "ChatGPT stream ended without a completed text response")
            return "".join(text)
        endpoint = store.load(user).get("endpoint")
        if not endpoint:
            raise HTTPException(409, "Configure an endpoint in Settings first")
        response = await http.post(
            endpoint["base_url"].rstrip("/") + "/chat/completions",
            headers={"Authorization": "Bearer " + endpoint["api_key"]} if endpoint.get("api_key") else {},
            json={
                "model": character["model"] or endpoint["model"],
                "messages": [{"role": "system", "content": instructions}, *history],
            },
        )
        if response.status_code != 200:
            raise HTTPException(502, f"Model endpoint failed ({response.status_code})")
        try:
            choice = response.json()["choices"][0]
            if choice.get("finish_reason") in {"length", "content_filter"}:
                raise HTTPException(502, "Model endpoint returned an incomplete reply")
            result = choice["message"]["content"]
            if not isinstance(result, str) or not result.strip() or len(result) > 64000:
                raise ValueError()
            return result
        except (KeyError, IndexError, ValueError):
            raise HTTPException(502, "Model endpoint returned no text") from None
