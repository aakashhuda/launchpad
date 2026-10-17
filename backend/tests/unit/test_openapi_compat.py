from __future__ import annotations

from scripts.openapi_compat import breaking_changes


def _spec(paths: dict, components: dict | None = None) -> dict:
    return {"paths": paths, "components": {"schemas": components or {}}}


def _op(schema: dict) -> dict:
    return {"responses": {"200": {"content": {"application/json": {"schema": schema}}}}}


def _object_schema(**properties: dict) -> dict:
    return {"type": "object", "properties": properties}


def test_identical_specs_have_no_breaking_changes():
    spec = _spec({"/x": {"get": _op(_object_schema(a={"type": "string"}))}})
    assert breaking_changes(spec, spec) == []


def test_added_property_is_not_breaking():
    old = _spec({"/x": {"get": _op(_object_schema(a={"type": "string"}))}})
    new = _spec({"/x": {"get": _op(_object_schema(a={"type": "string"}, b={"type": "integer"}))}})
    assert breaking_changes(old, new) == []


def test_removed_property_is_breaking():
    old = _spec({"/x": {"get": _op(_object_schema(a={"type": "string"}, b={"type": "integer"}))}})
    new = _spec({"/x": {"get": _op(_object_schema(a={"type": "string"}))}})
    changes = breaking_changes(old, new)
    assert any("property removed" in change and "b" in change for change in changes)


def test_type_change_is_breaking():
    old = _spec({"/x": {"get": _op(_object_schema(a={"type": "string"}))}})
    new = _spec({"/x": {"get": _op(_object_schema(a={"type": "integer"}))}})
    assert any("type changed" in change for change in breaking_changes(old, new))


def test_removed_path_is_breaking():
    old = _spec({"/x": {"get": _op({"type": "object"})}, "/y": {"get": _op({"type": "object"})}})
    new = _spec({"/x": {"get": _op({"type": "object"})}})
    assert "path removed: /y" in breaking_changes(old, new)


def test_removed_operation_is_breaking():
    old = _spec({"/x": {"get": _op({"type": "object"}), "post": _op({"type": "object"})}})
    new = _spec({"/x": {"get": _op({"type": "object"})}})
    assert "operation removed: POST /x" in breaking_changes(old, new)


def test_newly_required_field_is_breaking():
    old = _spec({"/x": {"get": _op(_object_schema(a={"type": "string"}))}})
    new = _spec(
        {
            "/x": {
                "get": _op(
                    {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
                )
            }
        }
    )
    assert any("became required" in change for change in breaking_changes(old, new))


def test_removed_enum_value_is_breaking():
    old = _spec({"/x": {"get": _op({"type": "string", "enum": ["a", "b"]})}})
    new = _spec({"/x": {"get": _op({"type": "string", "enum": ["a"]})}})
    assert any("enum values removed" in change for change in breaking_changes(old, new))


def test_ref_resolution_detects_removed_component_property():
    old = _spec(
        {"/x": {"get": _op({"$ref": "#/components/schemas/Thing"})}},
        {"Thing": _object_schema(a={"type": "string"}, b={"type": "string"})},
    )
    new = _spec(
        {"/x": {"get": _op({"$ref": "#/components/schemas/Thing"})}},
        {"Thing": _object_schema(a={"type": "string"})},
    )
    assert any("property removed" in change for change in breaking_changes(old, new))


def test_request_body_newly_required_field_is_breaking():
    def op(request_schema: dict) -> dict:
        return {
            "requestBody": {"content": {"application/json": {"schema": request_schema}}},
            "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}},
        }

    old = _spec({"/x": {"post": op(_object_schema(a={"type": "string"}))}})
    new = _spec(
        {
            "/x": {
                "post": op(
                    {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
                )
            }
        }
    )
    assert any("became required" in change for change in breaking_changes(old, new))
