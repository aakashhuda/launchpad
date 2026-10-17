"""Detect breaking changes between two OpenAPI schemas.

Used by CI to guard the committed baseline: a PR that removes/renames a
response field, changes a field type, drops an endpoint, or makes an optional
field required fails the check. Purely additive changes (new endpoints, new
optional fields, new enum values) are allowed up to the whole-spec equality
check in CI, which should be refreshed deliberately.

Usage:
    python scripts/openapi_compat.py <baseline.json> <current.json>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def _resolve(spec: dict, node: Any, seen: frozenset[str] = frozenset()) -> Any:
    """Follow ``$ref`` pointers within ``spec`` (guarding against cycles)."""
    if isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if ref in seen:
            return node
        target: Any = spec
        for part in ref.lstrip("#/").split("/"):
            target = target[part]
        return _resolve(spec, target, seen | {ref})
    return node


def _diff_schema(
    old_spec: dict,
    new_spec: dict,
    old: Any,
    new: Any,
    path: str,
    out: list[str],
    seen: set[tuple[int, int]],
) -> None:
    old = _resolve(old_spec, old)
    new = _resolve(new_spec, new)
    if not isinstance(old, dict) or not isinstance(new, dict):
        return

    pair = (id(old), id(new))
    if pair in seen:
        return
    seen.add(pair)

    old_type = old.get("type")
    new_type = new.get("type")
    if old_type and new_type and old_type != new_type:
        out.append(f"{path}: type changed from {old_type!r} to {new_type!r}")
        return

    if "enum" in old:
        new_enum = set(new.get("enum", []))
        removed = [value for value in old["enum"] if value not in new_enum]
        if removed:
            out.append(f"{path}: enum values removed: {removed}")

    if old_type == "object" or "properties" in old:
        old_props = old.get("properties", {})
        new_props = new.get("properties", {})
        old_required = set(old.get("required", []))
        new_required = set(new.get("required", []))
        for name, old_prop in old_props.items():
            if name not in new_props:
                out.append(f"{path}.{name}: property removed")
                continue
            if name not in old_required and name in new_required:
                out.append(f"{path}.{name}: property became required")
            _diff_schema(old_spec, new_spec, old_prop, new_props[name], f"{path}.{name}", out, seen)

    if "items" in old:
        if "items" not in new:
            out.append(f"{path}: array items schema removed")
        else:
            _diff_schema(old_spec, new_spec, old["items"], new["items"], f"{path}[]", out, seen)

    for keyword in ("anyOf", "oneOf", "allOf"):
        if keyword not in old:
            continue
        old_branches = old[keyword]
        new_branches = new.get(keyword)
        if not new_branches:
            out.append(f"{path}: {keyword} removed")
            continue
        for index, branch in enumerate(old_branches):
            if index < len(new_branches):
                _diff_schema(
                    old_spec,
                    new_spec,
                    branch,
                    new_branches[index],
                    f"{path}<{keyword}[{index}]>",
                    out,
                    seen,
                )
            else:
                out.append(f"{path}: {keyword} branch removed at index {index}")


def _diff_content(
    old_spec: dict,
    new_spec: dict,
    old_content: dict,
    new_content: dict,
    path: str,
    out: list[str],
) -> None:
    old_schema = (old_content or {}).get("application/json", {}).get("schema")
    if old_schema is None:
        return
    new_schema = (new_content or {}).get("application/json", {}).get("schema")
    if new_schema is None:
        out.append(f"{path}: application/json schema removed")
        return
    _diff_schema(old_spec, new_spec, old_schema, new_schema, path, out, set())


def breaking_changes(old_spec: dict, new_spec: dict) -> list[str]:
    """Return human-readable descriptions of breaking changes (empty if none)."""
    out: list[str] = []
    old_paths = old_spec.get("paths", {})
    new_paths = new_spec.get("paths", {})

    for path, old_item in old_paths.items():
        if path not in new_paths:
            out.append(f"path removed: {path}")
            continue
        new_item = new_paths[path]
        for method, old_op in old_item.items():
            if method not in _METHODS:
                continue
            label = f"{method.upper()} {path}"
            if method not in new_item:
                out.append(f"operation removed: {label}")
                continue
            new_op = new_item[method]

            old_responses = old_op.get("responses", {})
            new_responses = new_op.get("responses", {})
            for code, old_resp in old_responses.items():
                if code not in new_responses:
                    out.append(f"{label}: response {code} removed")
                    continue
                _diff_content(
                    old_spec,
                    new_spec,
                    old_resp.get("content", {}),
                    new_responses[code].get("content", {}),
                    f"{label} [{code}]",
                    out,
                )

            old_body = old_op.get("requestBody")
            new_body = new_op.get("requestBody")
            if old_body is not None:
                if new_body is None:
                    out.append(f"{label}: request body removed")
                else:
                    _diff_content(
                        old_spec,
                        new_spec,
                        old_body.get("content", {}),
                        new_body.get("content", {}),
                        f"{label} (request)",
                        out,
                    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Check for breaking OpenAPI changes.")
    parser.add_argument("baseline", type=Path, help="Committed baseline schema.")
    parser.add_argument("current", type=Path, help="Freshly generated schema.")
    args = parser.parse_args()

    old_spec = json.loads(args.baseline.read_text(encoding="utf-8"))
    new_spec = json.loads(args.current.read_text(encoding="utf-8"))
    changes = breaking_changes(old_spec, new_spec)
    if changes:
        print("Breaking API changes detected:")
        for change in changes:
            print(f"  - {change}")
        return 1
    print("No breaking API changes detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
