import asyncio
import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException

from .config import settings
from .credentials import store

ISSUER = "https://auth.openai.com"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
USAGE_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = "openid profile email offline_access resource.invoke " + USAGE_SCOPE
pending: dict[str, dict] = {}
locks: dict[str, asyncio.Lock] = {}


def lock(user):
    return locks.setdefault(user, asyncio.Lock())


def start(user: str, account: str | None = None) -> str:
    for state, value in list(pending.items()):
        if value["expires"] < time.time():
            pending.pop(state, None)
    if len(pending) > 100:
        raise HTTPException(429, "Too many sign-in attempts")
    data = store.load(user)
    saved = data["accounts"].get(account) if account else None
    if account and not saved:
        raise HTTPException(404, "Account registration not found")
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    client = saved["client_id"] if saved else "dynamic_agent_client"
    pending[state] = {
        "user": user,
        "nonce": nonce,
        "verifier": verifier,
        "client_id": client,
        "subject": saved.get("subject") if saved else None,
        "redirect": settings.chatgpt_callback,
        "expires": time.time() + 600,
    }
    query = {
        "client_id": client,
        "ext_agent_host_id": store.host_id(),
        "response_type": "code",
        "redirect_uri": settings.chatgpt_callback,
        "scope": SCOPES,
        "resource": RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("="),
    }
    if saved:
        if saved.get("id_token"):
            query["id_token_hint"] = saved["id_token"]
    else:
        query["agent_name_hint"] = "AI Character"
    return AUTHORIZE + "?" + urlencode(query)


async def validate_identity(token: str, client: str, nonce: str | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15) as http:
        discovery = await http.get(ISSUER + "/.well-known/openid-configuration")
        discovery.raise_for_status()
        jwks = await http.get(discovery.json()["jwks_uri"])
        jwks.raise_for_status()
    header = jwt.get_unverified_header(token)
    key = next((k for k in jwks.json()["keys"] if k["kid"] == header.get("kid")), None)
    if not key:
        raise ValueError("Unknown signing key")
    claims = jwt.decode(
        token,
        jwt.PyJWK.from_dict(key).key,
        algorithms=["RS256"],
        audience=client,
        issuer=ISSUER,
        options={"require": ["exp", "iss", "aud", "sub"]},
    )
    if nonce is not None and not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise ValueError("Nonce mismatch")
    return claims


async def callback(state: str, code: str | None, client_id: str | None, error: str | None):
    attempt = pending.pop(state, None)
    if not attempt or attempt["expires"] < time.time():
        raise HTTPException(400, "Sign-in attempt expired or invalid; start again")
    if error or not code:
        raise HTTPException(400, "ChatGPT authorization was not completed")
    client = attempt["client_id"]
    if client == "dynamic_agent_client":
        if not client_id or client_id == client:
            raise HTTPException(400, "Registration did not return an issued client ID")
        client = client_id
    elif client_id and client_id != client:
        raise HTTPException(400, "Registration mismatch")
    async with lock(attempt["user"]):
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.post(
                TOKEN,
                data={
                    "grant_type": "authorization_code",
                    "client_id": client,
                    "code": code,
                    "code_verifier": attempt["verifier"],
                    "redirect_uri": attempt["redirect"],
                    "resource": RESOURCE,
                },
            )
        if response.status_code != 200:
            raise HTTPException(400, "Code exchange failed; restart sign-in")
        tokens = response.json()
        try:
            identity = await validate_identity(tokens["id_token"], client, attempt["nonce"])
        except Exception:
            raise HTTPException(400, "ChatGPT identity validation failed") from None
        if attempt["subject"] and identity["sub"] != attempt["subject"]:
            raise HTTPException(400, "Selected account identity changed")
        scopes = tokens.get("scope", "").split()
        if USAGE_SCOPE not in scopes:
            raise HTTPException(403, "ChatGPT plan usage permission was not granted")
        data = store.load(attempt["user"])
        data["accounts"][client] = {
            "client_id": client,
            "subject": identity["sub"],
            "email": identity.get("email", "ChatGPT account"),
            "scopes": scopes,
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "id_token": tokens["id_token"],
            "expires_at": time.time() + tokens.get("expires_in", 3600),
        }
        data["active"] = client
        store.save(attempt["user"], data)


async def access_token(user: str) -> str:
    async with lock(user):
        data = store.load(user)
        account = data["accounts"].get(data.get("active"))
        if not account or not account.get("access_token"):
            raise HTTPException(409, "Connect ChatGPT in Settings first")
        if account["expires_at"] > time.time() + 90:
            return account["access_token"]
        if not account.get("refresh_token"):
            raise HTTPException(401, "ChatGPT session expired; reconnect")
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.post(
                TOKEN,
                data={
                    "grant_type": "refresh_token",
                    "client_id": account["client_id"],
                    "refresh_token": account["refresh_token"],
                    "resource": RESOURCE,
                },
            )
        if response.status_code != 200:
            raise HTTPException(401, "ChatGPT refresh failed; reconnect")
        tokens = response.json()
        scopes = tokens.get("scope", " ".join(account["scopes"])).split()
        if USAGE_SCOPE not in scopes:
            raise HTTPException(403, "ChatGPT plan permission is no longer available")
        if tokens.get("id_token"):
            claims = await validate_identity(tokens["id_token"], account["client_id"])
            if claims["sub"] != account["subject"]:
                raise HTTPException(401, "ChatGPT account identity changed")
            account["id_token"] = tokens["id_token"]
        account.update(
            access_token=tokens["access_token"],
            scopes=scopes,
            refresh_token=tokens.get("refresh_token", account["refresh_token"]),
            expires_at=time.time() + tokens.get("expires_in", 3600),
        )
        store.save(user, data)
        return account["access_token"]


async def disconnect(user: str, client: str) -> bool:
    async with lock(user):
        data = store.load(user)
        account = data["accounts"].get(client)
        if not account:
            raise HTTPException(404, "Account not found")
        confirmed = not account.get("refresh_token")
        if account.get("refresh_token"):
            try:
                async with httpx.AsyncClient(timeout=15) as http:
                    discovery = await http.get(ISSUER + "/.well-known/openid-configuration")
                    discovery.raise_for_status()
                    endpoint = discovery.json()["revocation_endpoint"]
                    for delay in [0, 1, 2]:
                        await asyncio.sleep(delay)
                        response = await http.post(
                            endpoint,
                            data={
                                "token": account["refresh_token"],
                                "token_type_hint": "refresh_token",
                                "client_id": client,
                            },
                        )
                        if response.status_code == 200:
                            confirmed = True
                            break
            except (httpx.HTTPError, KeyError, ValueError):
                pass
        for key in ["access_token", "refresh_token", "id_token"]:
            account.pop(key, None)
        if data.get("active") == client:
            data["active"] = None
        store.save(user, data)
        return confirmed
