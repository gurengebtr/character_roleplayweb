"""Run the three runtimes, stop siblings on exit; secrets inherited from root .env."""

import os
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
if not (ROOT / ".venv/bin/python").exists():
    raise SystemExit("Run ./setup.sh first.")
# Use the installed dotenv parser, even when npm launched us with system Python.
if Path(os.sys.prefix).resolve() != (ROOT / ".venv").resolve():
    os.execv(str(ROOT / ".venv/bin/python"), [str(ROOT / ".venv/bin/python"), __file__])
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
env = dict(os.environ, PYTHONPATH=f"{ROOT}/services/api:{ROOT}/services/rag:{ROOT}")


def port(key, default):
    url = urlparse(env.get(key, default))
    if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port:
        raise SystemExit(f"{key} must be an http://127.0.0.1:PORT URL for local use")
    return str(url.port)


commands = [
    [
        str(ROOT / ".venv/bin/python"),
        "-m",
        "uvicorn",
        "ai_character_api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        port("API_URL", "http://127.0.0.1:8100"),
        "--no-access-log",
    ],
    [
        str(ROOT / ".venv/bin/python"),
        "-m",
        "uvicorn",
        "ai_character_rag.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        port("RAG_URL", "http://127.0.0.1:8101"),
    ],
    [
        "npm",
        "run",
        "dev",
        "--workspace",
        "apps/web",
        "--",
        "--port",
        port("WEB_URL", "http://127.0.0.1:3100"),
    ],
]
processes = []


def stop(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    for command in commands:
        processes.append(subprocess.Popen(command, env=env, start_new_session=True))
    print(f"AI Character: {env.get('WEB_URL', 'http://127.0.0.1:3100')}", flush=True)
    while all(p.poll() is None for p in processes):
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    # npm and the test runner may both forward SIGTERM; cleanup is idempotent.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    for p in processes:
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for p in processes:
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
