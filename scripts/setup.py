"""Idempotent local provisioning; unknown resources and incompatible schema are never adopted."""

import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from pymongo import MongoClient
from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
COMPOSE = ROOT / "deploy/local/compose.yaml"
MANIFEST = ROOT / ".local/install.json"
CHECK = "--check" in sys.argv
sys.path.insert(0, str(ROOT))
from scripts.schema import inspect_schema  # noqa: E402


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def write_private(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(content)


def main():
    os.chdir(ROOT)
    if not (ROOT / ".env").exists():
        if CHECK:
            raise SystemExit("missing .env; run ./setup.sh")
        values = {
            "AUTH_SECRET": secrets.token_urlsafe(48),
            "SERVICE_TOKEN": secrets.token_urlsafe(48),
            "CREDENTIAL_KEY": Fernet.generate_key().decode(),
            "BOOTSTRAP_PASSWORD": secrets.token_urlsafe(18),
        }
        content = (ROOT / ".env.example").read_text()
        for key, value in values.items():
            content = content.replace(f"{key}=\n", f"{key}={value}\n")
        write_private(ROOT / ".env", content)
        print("Created .env (0600); your local login password is stored there, not printed.")
    load_dotenv(ROOT / ".env")
    for key in ["AUTH_SECRET", "SERVICE_TOKEN", "CREDENTIAL_KEY", "BOOTSTRAP_PASSWORD"]:
        if not os.environ.get(key):
            raise SystemExit(f"missing {key} in .env")
    from ai_character_api.auth import hash_password
    from ai_character_api.config import settings

    if (
        settings.mongo_uri != "mongodb://127.0.0.1:27028"
        or os.environ["QDRANT_URL"] != "http://127.0.0.1:6338"
    ):
        raise SystemExit(
            "MVP setup only manages its dedicated local ports 27028 and 6338; external databases require manual provisioning"
        )
    desired = {
        "schema_version": 1,
        "compose_sha256": hashlib.sha256(COMPOSE.read_bytes()).hexdigest(),
        "embedding_model": os.environ["EMBEDDING_MODEL"],
        "embedding_dim": int(os.environ["EMBEDDING_DIM"]),
        "mongo_db": settings.mongo_db,
        "qdrant_prefix": os.environ["QDRANT_PREFIX"],
        "root": str(ROOT),
    }
    saved = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else None
    if saved and any(saved.get(k) != v for k, v in desired.items()):
        for key, value in desired.items():
            if saved.get(key) != value:
                print(f"changed manifest.{key}: explicit migration/review required")
        raise SystemExit(2)
    if not saved:
        volumes = run("docker", "volume", "ls", "--format", "{{.Name}}")
        if any(x.startswith("ai-character-mvp_") for x in volumes.splitlines()):
            raise SystemExit("unknown existing project volumes without install manifest; refusing adoption")
        for port in [27028, 6338]:
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    raise SystemExit(f"unknown service on port {port}; refusing adoption")
        if CHECK:
            raise SystemExit("missing local installation")
        # Manifest is written before provisioning so interrupted installs can resume.
        write_private(MANIFEST, json.dumps(desired, indent=2) + "\n")
    # Even with a manifest, never adopt another checkout's containers.
    container_ids = run(
        "docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=ai-character-mvp"
    ).splitlines()
    for identity in container_ids:
        info = json.loads(run("docker", "inspect", identity))[0]
        labels = info["Config"].get("Labels", {})
        if labels.get("ai.character.managed") != "true" or labels.get(
            "com.docker.compose.project.working_dir"
        ) != str(COMPOSE.parent):
            raise SystemExit("unknown container ownership; refusing to update")
    for volume in ["ai-character-mvp_mongo-data", "ai-character-mvp_qdrant-data"]:
        result = subprocess.run(["docker", "volume", "inspect", volume], capture_output=True, text=True)
        if result.returncode == 0:
            labels = json.loads(result.stdout)[0].get("Labels") or {}
            if labels.get("com.docker.compose.project") != "ai-character-mvp":
                raise SystemExit("unknown volume ownership; refusing to update")
    if not CHECK:
        subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE), "up", "-d", "--wait", "--wait-timeout", "120"],
            check=True,
        )
    mongo = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=2000)
    db = mongo[settings.mongo_db]
    qurl = os.environ["QDRANT_URL"]
    if not CHECK:
        for _ in range(60):
            try:
                mongo.admin.command("ping")
                httpx.get(f"{qurl}/readyz", timeout=2).raise_for_status()
                break
            except Exception:
                time.sleep(1)
        else:
            raise SystemExit("databases did not become healthy")
    mongo.admin.command("ping")
    q = QdrantClient(url=qurl, timeout=5)
    additions, conflicts, notices = inspect_schema(
        db, q, os.environ["QDRANT_PREFIX"], desired["embedding_dim"]
    )
    for notice in notices:
        print(notice)
    for conflict in conflicts:
        print("changed: " + conflict)
    for label, _ in additions:
        print("missing: " + label)
    changed = bool(conflicts or (CHECK and additions))
    if not CHECK and not conflicts:
        for _, apply in additions:
            apply()
    if not CHECK and not changed:
        username = os.environ.get("BOOTSTRAP_USERNAME", "admin")
        if not db.users.find_one({"username": username}):
            db.users.insert_one(
                {
                    "user_id": secrets.token_hex(16),
                    "username": username,
                    "password_hash": hash_password(os.environ["BOOTSTRAP_PASSWORD"]),
                }
            )
        db.settings.update_one({"key": "schema"}, {"$setOnInsert": {"version": 1}}, upsert=True)
    mongo.close()
    q.close()
    if changed:
        raise SystemExit(2)
    print("same: managed manifest, Mongo indexes and Qdrant schema are compatible.")
    print("Ready. Run npm run dev → http://127.0.0.1:3100")


if __name__ == "__main__":
    main()
