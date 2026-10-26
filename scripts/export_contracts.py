"""Generate API contracts from the running application's Pydantic schemas."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "services/rag"))
from ai_character_api.main import app as api  # noqa: E402
from ai_character_rag.main import app as rag  # noqa: E402

for name, app in [("api", api), ("rag", rag)]:
    (ROOT / f"packages/contracts/{name}.openapi.json").write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"
    )
