"""Configuration loaded from environment variables.

All knobs in one place so the agent and harness share the same source of truth.
Loaded via python-dotenv from .env in the project root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root, regardless of where Python is invoked from
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_PATH)


def _get_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in {"1", "true", "yes", "y"}


def _get_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    return float(raw) if raw else default


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    """All tunable parameters for the agent and harness."""

    # --- LLM provider ---
    openai_api_key: str
    llm_model: str
    memory_model: str
    embedding_model: str
    embedding_dims: int

    # --- Decision thresholds ---
    deny_threshold: float
    stepup_threshold: float

    # --- Memory ---
    session_window: int
    memory_k: int

    # --- Behavior toggles ---
    llm_validate_always: bool
    debug: bool

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        return cls(
            openai_api_key=api_key,
            llm_model=os.getenv("ZT_PDP_LLM_MODEL", "gpt-4o-mini"),
            memory_model=os.getenv("ZT_PDP_MEMORY_MODEL", "gpt-4o-mini"),
            embedding_model=os.getenv("ZT_PDP_EMBEDDING_MODEL", "text-embedding-3-small"),
            embedding_dims=_get_int("ZT_PDP_EMBEDDING_DIMS", 1536),
            deny_threshold=_get_float("ZT_PDP_DENY_THRESHOLD", 0.75),
            stepup_threshold=_get_float("ZT_PDP_STEPUP_THRESHOLD", 0.45),
            session_window=_get_int("ZT_PDP_SESSION_WINDOW", 8),
            memory_k=_get_int("ZT_PDP_MEMORY_K", 5),
            llm_validate_always=_get_bool("ZT_PDP_LLM_VALIDATE_ALWAYS", False),
            debug=_get_bool("ZT_PDP_DEBUG", False),
        )
