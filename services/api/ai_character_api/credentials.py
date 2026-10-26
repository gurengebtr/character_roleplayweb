"""Local encrypted records, never returned by domain endpoints."""

import json
import os
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet

from .config import settings


class CredentialStore:
    def __init__(self, directory: Path | None = None, key: str | None = None):
        self.directory = directory or settings.credential_dir
        self.key = key or settings.credential_key

    def load(self, user: str) -> dict:
        path = self.directory / (sha256(user.encode()).hexdigest() + ".enc")
        if not path.exists():
            return {"accounts": {}, "active": None}
        return json.loads(Fernet(self.key.encode()).decrypt(path.read_bytes()))

    def save(self, user: str, data: dict):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.directory / (sha256(user.encode()).hexdigest() + ".enc")
        temp = self.directory / (uuid4().hex + ".tmp")
        token = Fernet(self.key.encode()).encrypt(json.dumps(data).encode())
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(token)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)

    def host_id(self) -> str:
        data = self.load("_host")
        if "host_id" not in data:
            data["host_id"] = "urn:uuid:" + str(uuid4())
            self.save("_host", data)
        return data["host_id"]


store = CredentialStore()
