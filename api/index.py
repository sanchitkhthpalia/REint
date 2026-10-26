"""Vercel Python serverless entrypoint: exposes the FastAPI app from backend/.

vercel.json rewrites /api/* here and bundles backend/app and data/ with this function.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402

__all__ = ["app"]
