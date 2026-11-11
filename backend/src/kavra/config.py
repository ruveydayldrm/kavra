"""Runtime configuration, read from environment / `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- Provider keys -----------------------------------------------------
    gemini_api_key: str = ""
    groq_api_key: str = ""
    ollama_url: str = "http://127.0.0.1:11434"

    # --- Role routing: "provider:model", comma-separated fallbacks ----------
    generator: str = "gemini:gemini-3.8-flash"
    generator_fallbacks: str = "gemini:gemini-3.5-flash-lite,ollama:qwen2.5:3b"
    auditor: str = "groq:openai/gpt-oss-120b"
    auditor_fallbacks: str = "groq:qwen/qwen3.8-27b,gemini:gemini-3.5-flash-lite"
    local_mode: bool = False  # force every role to Ollama (nothing leaves the machine)
    local_model: str = "qwen2.5:3b"

    # --- Free-tier budgets (per model; check your console, these are conservative) --
    gemini_rpm: int = 8
    gemini_tpm: int = 200_000
    gemini_rpd: int = 200
    groq_rpm: int = 25
    groq_tpm: int = 7_000
    groq_rpd: int = 900
    ollama_rpm: int = 1000

    # --- Pipeline ---------------------------------------------------------
    questions_per_chunk: int = 4
    chunk_chars: int = 1600
    dedup_threshold: float = 0.88
    quote_match_threshold: float = 88.0
    max_repairs: int = 1
    single_model: bool = False  # ablation: skip the auditor stage

    # --- Study ------------------------------------------------------------
    new_cards_per_day: int = 20
    desired_retention: float = 0.9

    # --- Infra ------------------------------------------------------------
    data_dir: Path = Field(default=ROOT / "data")
    embedder: str = "minilm"  # "minilm" | "hash"
    embed_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    hf_home: str = ""
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "kavra.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    if s.hf_home:
        import os

        os.environ.setdefault("HF_HOME", s.hf_home)
    return s
