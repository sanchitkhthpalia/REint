"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORS_ORIGINS = "http://localhost:5173"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = REPO_ROOT / "data"
    # Origins allowed to call the API from a browser. Empty = CORS disabled (same-origin only).
    cors_origins: tuple[str, ...] = (DEFAULT_CORS_ORIGINS,)
    cache_size: int = 128
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> Settings:
        """DATA_DIR, CORS_ORIGINS (comma-separated, or "*"), CACHE_SIZE, LOG_LEVEL."""
        origins = os.environ.get("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
        return cls(
            data_dir=Path(os.environ.get("DATA_DIR", str(REPO_ROOT / "data"))),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
            cache_size=int(os.environ.get("CACHE_SIZE", "128")),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )
