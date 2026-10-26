"""Write the API's OpenAPI schema to backend/openapi.json (source for frontend types).

Usage (from the repo root, backend installed):
    python scripts/export_openapi.py && (cd frontend && npm run gen:api)
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

OUT = Path(__file__).resolve().parent.parent / "backend" / "openapi.json"


def main() -> None:
    OUT.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
