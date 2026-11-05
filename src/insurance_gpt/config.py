from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration. Every field can be overridden by an `IGPT_*` env var or `.env`."""

    model_config = SettingsConfigDict(env_prefix="IGPT_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    knowledge_dir: Path = PROJECT_ROOT / "knowledge"
    qdrant_path: Path = PROJECT_ROOT / ".data" / "qdrant"
    collection: str = "conditions"
    embedding_model: str = "intfloat/multilingual-e5-base"

    @property
    def sources_file(self) -> Path:
        return self.knowledge_dir / "sources.yaml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
