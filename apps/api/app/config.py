import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "infra/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM & Models
    LLM_PROVIDER: str = "gemini"
    ANSWER_MODEL: str = ""
    VISION_MODEL: str = ""
    LLM_FALLBACK_CHAIN: str = ""
    GEMINI_API_KEY: str = ""
    OLLAMA_URL: str = "http://localhost:11434"
    LLM_DAILY_CAP: int = 0

    # Web Research (Spoiler ON/OFF)
    TAVILY_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    RESEARCH_MODEL: str = "llama-3.3-70b-versatile"
    FEATURE_WEB_MODE: bool = False
    WEB_SEARCH_ENABLED: bool = False
    TAVILY_MAX_RESULTS: int = 5
    TAVILY_TIMEOUT_S: float = 15.0
    GROQ_TIMEOUT_S: float = 25.0
    GROQ_MAX_TOKENS: int = 700
    RESEARCH_CONTEXT_TOKEN_CAP: int = 3000
    TAVILY_CACHE_TTL_HOURS: int = 24

    # Database & Storage
    DATABASE_URL: str = "postgresql://pause:pause@localhost:5432/pause"
    DATA_DIR: str = "./data"
    EMBEDDED_WORKER: bool = True
    AUTO_SEED_DEMO: bool = True

    # Auth & Security
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    ALLOWED_ORIGINS: str = "http://localhost:5173"
    PUBLIC_API_URL: str = "http://localhost:8000"

    # Media & OCR tools
    FFMPEG_PATH: str = "ffmpeg"
    FFPROBE_PATH: str = "ffprobe"
    TESSERACT_CMD: str = "tesseract"
    WHISPER_MODEL: str = "small"
    WHISPER_COMPUTE: str = "int8"

    # Retrieval & Embedding
    EMBEDDING_BACKEND: str = "local"  # "local" (vector+fts) or "fts" (cloud-safe PostgreSQL full-text search)
    EMBED_MODEL: str = "intfloat/multilingual-e5-small"
    RERANK_ENABLED: bool = False
    TOPK: int = 8
    CONTEXT_TOKEN_CAP: int = 3500
    RECENT_WINDOW_S: int = 60
    RECENT_WINDOW_WIDE_S: int = 180
    RECENT_MIN_WORDS: int = 20
    REFUSAL_SCORE_THRESHOLD: Optional[float] = 0.5
    ALIGN_TAU: Optional[float] = 0.5
    VISION_CALLS_PER_VIDEO_CAP: int = 100

    # Limits & Constraints
    MAX_VIDEO_HOURS: int = 3
    MAX_UPLOAD_MB: int = 2048
    RATE_LIMIT_PER_MIN: int = 30
    YT_COOKIES_FILE: str = ""

    # Interview
    INTERVIEW_MAX_MINUTES: int = 10
    INTERVIEW_MAX_TURNS: int = 8
    INTERVIEW_WEIGHTS: str = "technical:0.4,communication:0.2,problem_solving:0.25,structure:0.15"

    # Pricing
    PRICE_IN_PER_MTOK: float = 0.0
    PRICE_OUT_PER_MTOK: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def resolve_feature_flags(cls, data: Any) -> Any:
        """
        1. FEATURE_WEB_MODE is canonical.
        2. Default is False when absent.
        3. WEB_SEARCH_ENABLED is supported as backward-compatible alias.
        4. If both are defined, FEATURE_WEB_MODE wins.
        """
        if isinstance(data, dict):
            feat = data.get("FEATURE_WEB_MODE")
            legacy = data.get("WEB_SEARCH_ENABLED")

            if feat is not None:
                if isinstance(feat, str):
                    resolved = feat.lower() in ("true", "1", "yes", "on")
                else:
                    resolved = bool(feat)
            elif legacy is not None:
                if isinstance(legacy, str):
                    resolved = legacy.lower() in ("true", "1", "yes", "on")
                else:
                    resolved = bool(legacy)
            else:
                resolved = False

            data["FEATURE_WEB_MODE"] = resolved
            data["WEB_SEARCH_ENABLED"] = resolved
        return data

    @field_validator("REFUSAL_SCORE_THRESHOLD", "ALIGN_TAU", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Union[str, float, None]) -> Optional[float]:
        if v is None or v == "":
            return None
        return float(v)

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    def resolved_tesseract_cmd(self) -> str:
        cmd = self.TESSERACT_CMD
        if shutil.which(cmd):
            return cmd
        candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
        ]
        for candidate in candidates:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
            if os.name == "nt" and os.path.isfile(candidate):
                return candidate
        return cmd

    def resolved_ffmpeg_cmd(self) -> str:
        cmd = self.FFMPEG_PATH
        if shutil.which(cmd):
            return cmd
        return cmd

    def resolved_ffprobe_cmd(self) -> str:
        cmd = self.FFPROBE_PATH
        if shutil.which(cmd):
            return cmd
        return cmd


@lru_cache()
def get_settings() -> Settings:
    return Settings()
