from __future__ import annotations

import json
from pathlib import Path

from scripts.export_openapi import export


def test_export_produces_versioned_spec(tmp_path: Path):
    output = tmp_path / "openapi.json"
    schema = export(output)

    assert output.is_file()
    reloaded = json.loads(output.read_text(encoding="utf-8"))
    assert reloaded == schema
    # The committed baseline must contain the versioned API surface.
    assert "/api/v1/health" in reloaded["paths"]
    assert "components" in reloaded
    assert reloaded["paths"]
