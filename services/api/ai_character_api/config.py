from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    mongo_uri: str = "mongodb://127.0.0.1:27028"
    mongo_db: str = "ai_character"
    rag_url: str = "http://127.0.0.1:8101"
    web_url: str = "http://127.0.0.1:3100"
    service_token: str = ""
    credential_key: str = ""
    credential_dir: Path = ROOT / ".local/credentials"
    chatgpt_callback: str = "http://127.0.0.1:8100/auth/callback"
    worker_enabled: bool = True


settings = Settings()
