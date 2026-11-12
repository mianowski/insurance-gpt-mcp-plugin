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
    # Public hostnames the server is reached under (tunnel or VM domain), comma-separated, e.g.
    # "my-demo.ngrok-free.app". Requests with any other Host header are rejected (DNS rebinding protection).
    public_hosts: str = ""

    knowledge_dir: Path = PROJECT_ROOT / "knowledge"
    data_dir: Path = PROJECT_ROOT / ".data"

    embedding_model: str = "intfloat/multilingual-e5-large"
    # None = in-memory Qdrant rebuilt at startup from cached embeddings; set a URL to use a Qdrant server.
    qdrant_url: str | None = None
    collection: str = "conditions"

    search_top_k: int = 5
    # Below this cosine similarity (best dense match) a search returns "no_relevant_passage".
    min_relevance: float = 0.81

    @property
    def public_host_list(self) -> list[str]:
        return [h.strip() for h in self.public_hosts.split(",") if h.strip()]

    @property
    def sources_file(self) -> Path:
        return self.knowledge_dir / "sources.yaml"

    @property
    def chunks_dir(self) -> Path:
        return self.knowledge_dir / "chunks"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"


@lru_cache
def get_settings() -> Settings:
    return Settings()
