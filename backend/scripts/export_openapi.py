"""Export the FastAPI OpenAPI schema to a committed JSON baseline.

CI regenerates the schema and compares it against ``backend/openapi.json``
(via ``scripts/openapi_compat.py``) so breaking API changes fail before merge.
After an intentional *additive* change, refresh the baseline:

    python scripts/export_openapi.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.main import app  # noqa: E402

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "openapi.json"


def export(output_path: Path) -> dict:
    schema = app.openapi()
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the Launchpad OpenAPI schema.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    export(args.output)
    print(f"Wrote OpenAPI schema to {args.output}")


if __name__ == "__main__":
    main()
