import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from ai_character_api import oauth, providers
from ai_character_api.credentials import CredentialStore
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException


@pytest.fixture
def vault(monkeypatch, tmp_path):
    store = CredentialStore(tmp_path, Fernet.generate_key().decode())
    monkeypatch.setattr(oauth, "store", store)
    oauth.pending.clear()
    return store


def test_pkce_and_encrypted_storage(vault):
    query = parse_qs(urlparse(oauth.start("u")).query)
    assert query["client_id"] == ["dynamic_agent_client"]
    assert query["code_challenge_method"] == ["S256"]
    assert "chatgpt.tokens.use.direct" in query["scope"][0]
    assert query["ext_agent_host_id"][0].startswith("urn:uuid:")
    assert len(query["code_challenge"][0]) == 43
    assert "verifier" not in query
    vault.save("u", {"accounts": {}, "active": None, "secret": "private-token"})
    assert all(b"private-token" not in p.read_bytes() for p in vault.directory.glob("*.enc"))
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in vault.directory.glob("*.enc"))


@pytest.mark.asyncio
async def test_callback_state_issued_client_and_replay(vault, monkeypatch):
    query = parse_qs(urlparse(oauth.start("u")).query)
    state = query["state"][0]
    exchanged = []

    def handler(request):
        exchanged.append(parse_qs(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "id_token": "signed-id",
                "access_token": "access",
                "refresh_token": "refresh",
                "scope": oauth.SCOPES,
                "expires_in": 3600,
            },
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        oauth.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler))
    )

    async def identity(token, client, nonce=None):
        assert client == "issued-client" and nonce == query["nonce"][0]
        return {"sub": "person", "email": "test@example.invalid"}

    monkeypatch.setattr(oauth, "validate_identity", identity)
    with pytest.raises(HTTPException):
        await oauth.callback("wrong", "code", "issued-client", None)
    await oauth.callback(state, "code", "issued-client", None)
    assert exchanged[0]["client_id"] == ["issued-client"]
    assert exchanged[0]["redirect_uri"] == [oauth.settings.chatgpt_callback]
    assert vault.load("u")["active"] == "issued-client"
    with pytest.raises(HTTPException):
        await oauth.callback(state, "code", "issued-client", None)
    returning = parse_qs(urlparse(oauth.start("u", "issued-client")).query)
    assert returning["client_id"] == ["issued-client"]
    with pytest.raises(HTTPException):
        await oauth.callback(returning["state"][0], "code", "another-client", None)


@pytest.mark.asyncio
async def test_real_signature_nonce_and_audience(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    key["kid"] = "key1"

    def handler(request):
        return httpx.Response(
            200, json={"keys": [key]} if request.url.path == "/keys" else {"jwks_uri": oauth.ISSUER + "/keys"}
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        oauth.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler))
    )
    claims = {"iss": oauth.ISSUER, "aud": "client", "sub": "user", "exp": time.time() + 60, "nonce": "nonce"}
    token = jwt.encode(claims, private, algorithm="RS256", headers={"kid": "key1"})
    assert (await oauth.validate_identity(token, "client", "nonce"))["sub"] == "user"
    with pytest.raises(ValueError):
        await oauth.validate_identity(token, "client", "incorrect")
    with pytest.raises(jwt.InvalidAudienceError):
        await oauth.validate_identity(token, "other", "nonce")


@pytest.mark.asyncio
@pytest.mark.parametrize("completed", [True, False])
async def test_responses_requires_completed_and_store_false(monkeypatch, completed):
    async def token(user):
        return "access"

    monkeypatch.setattr(oauth, "access_token", token)

    def handler(request):
        payload = json.loads(request.content)
        assert payload["store"] is False and payload["stream"] is True
        events = [{"type": "response.output_text.delta", "delta": "你好"}]
        if completed:
            events.append({"type": "response.completed"})
        return httpx.Response(200, text="\n\n".join("data: " + json.dumps(e) for e in events))

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        providers.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler))
    )
    if completed:
        assert (
            await providers.generate("u", {"provider": "chatgpt", "model": "available-model"}, "role", [])
            == "你好"
        )
    else:
        with pytest.raises(HTTPException):
            await providers.generate("u", {"provider": "chatgpt", "model": "available-model"}, "role", [])


@pytest.mark.asyncio
async def test_refresh_is_serialized_and_rotated(vault, monkeypatch):
    import asyncio

    vault.save(
        "u",
        {
            "active": "client",
            "accounts": {
                "client": {
                    "client_id": "client",
                    "subject": "person",
                    "email": "test@example.invalid",
                    "access_token": "old-access",
                    "refresh_token": "old-refresh",
                    "expires_at": 0,
                    "scopes": oauth.SCOPES.split(),
                }
            },
        },
    )
    exchanges = []

    def handler(request):
        exchanges.append(parse_qs(request.content.decode()))
        return httpx.Response(
            200, json={"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        oauth.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler))
    )
    assert await asyncio.gather(oauth.access_token("u"), oauth.access_token("u")) == [
        "new-access",
        "new-access",
    ]
    assert len(exchanges) == 1 and exchanges[0]["client_id"] == ["client"]
    assert vault.load("u")["accounts"]["client"]["refresh_token"] == "new-refresh"


@pytest.mark.asyncio
async def test_disconnect_clears_credentials_even_if_remote_revocation_fails(vault, monkeypatch):
    vault.save(
        "u",
        {
            "active": "client",
            "accounts": {
                "client": {
                    "client_id": "client",
                    "subject": "person",
                    "email": "test@example.invalid",
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "id_token": "identity",
                }
            },
        },
    )

    def handler(request):
        raise httpx.ConnectError("offline")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        oauth.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler))
    )
    assert not await oauth.disconnect("u", "client")
    data = vault.load("u")
    assert data["active"] is None
    assert data["accounts"]["client"]["client_id"] == "client"
    assert not {"access_token", "refresh_token", "id_token"} & data["accounts"]["client"].keys()
