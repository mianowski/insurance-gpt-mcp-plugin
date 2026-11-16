"""Quality knobs (chunking, retrieval, prompts, evaluation targets), loaded from tuning.yaml.

Runtime/infrastructure settings (host, port, paths, Qdrant URL) stay in config.Settings; everything that
changes how good the answers are lives in the tuning file. All keys are required and unknown keys are
rejected, so a typo fails at startup instead of silently using a default.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from insurance_gpt.config import get_settings


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Chunking(_Strict):
    max_chars: int
    target_chars: int
    min_preamble_chars: int


class Retrieval(_Strict):
    dense_model: str
    sparse_model: str
    sparse_language: str
    embed_headings: bool
    mode: Literal["hybrid", "dense", "sparse"]
    search_with_question: bool
    prefetch_limit: int
    top_k: int
    max_top_k: int
    min_relevance: float


class ToolTexts(_Strict):
    list_documents: str
    search_conditions: str
    search_query: str
    get_section: str


class Answer(_Strict):
    disclaimer: str
    rules: list[str]
    server_instructions: str
    tools: ToolTexts
    scope_note: str
    result_guidance: str
    no_result_guidance: str

    @property
    def rules_text(self) -> str:
        """The rules as one text, "Rules: (0) … (1) …", with the disclaimer filled in."""
        rules = (r.replace("{disclaimer}", self.disclaimer) for r in self.rules)
        return "Rules: " + " ".join(f"({i}) {r}" for i, r in enumerate(rules))

    def render(self, text: str) -> str:
        return text.replace("{rules}", self.rules_text).replace("{disclaimer}", self.disclaimer)


class Evaluation(_Strict):
    k: int
    min_hit_at_k: float
    min_mrr: float
    min_rejection_rate: float


class Tuning(_Strict):
    chunking: Chunking
    retrieval: Retrieval
    answer: Answer
    evaluation: Evaluation
    source: Path | None = None  # the file it was loaded from (not a knob)

    @model_validator(mode="after")
    def _consistent(self) -> "Tuning":
        if not 0 < self.chunking.target_chars <= self.chunking.max_chars:
            raise ValueError("chunking: need 0 < target_chars <= max_chars")
        if not 1 <= self.retrieval.top_k <= self.retrieval.max_top_k:
            raise ValueError("retrieval: need 1 <= top_k <= max_top_k")
        return self


def load_tuning(path: Path) -> Tuning:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    try:
        return Tuning(**data, source=path)
    except ValueError as e:
        raise ValueError(f"Invalid tuning file {path}:\n{e}") from e


@lru_cache
def get_tuning() -> Tuning:
    return load_tuning(get_settings().tuning_file)
