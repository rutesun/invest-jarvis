"""OpenAI strict structured-output 스키마 계약 walker.

OpenAI strict 모드는 properties 없이 additionalProperties: false도 아닌
object(자유형 dict)와 items: {} (list[Any])를 서버 측에서 HTTP 400으로 거부한다.
클라이언트 측 변환기(convert_to_openai_tool 등)는 이를 잡지 못하므로,
서버가 강제하는 규칙을 그대로 재현해 모델 스키마를 검사한다.

원본: tests/pipelines/stock_report/test_synthesis_schema_strict.py (commit 94f55e4 회귀 가드)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


_OBJECT_COMBINATORS = ("anyOf", "oneOf", "allOf")


def _scan_schema(schema: dict[str, Any], path: str) -> list[str]:
    """Return locations of object schemas that OpenAI strict mode would reject.

    A node is unsafe when it is an object that neither declares ``properties`` nor
    pins ``additionalProperties: false`` — i.e. a ``dict[str, Any]``-style open
    object.  ``$ref`` nodes are skipped because their target ``$defs`` entry is
    scanned on its own.
    """
    bad: list[str] = []

    def walk(node: Any, where: str) -> None:
        if not isinstance(node, dict):
            return
        if node == {}:
            bad.append(where)  # list[Any] produces items: {} — untyped, rejected server-side
            return
        if "$ref" in node:
            return
        for combo in _OBJECT_COMBINATORS:
            for index, sub in enumerate(node.get(combo, []) or []):
                walk(sub, f"{where}.{combo}[{index}]")
        if node.get("type") == "object":
            props = node.get("properties")
            additional = node.get("additionalProperties", None)
            if not props and additional is not False:
                bad.append(where)
            for name, sub in (props or {}).items():
                walk(sub, f"{where}.{name}")
            if isinstance(additional, dict):
                walk(additional, f"{where}.<additionalProperties>")
        items = node.get("items")
        if isinstance(items, dict):
            walk(items, f"{where}[]")
        for index, sub in enumerate(node.get("prefixItems", []) or []):
            walk(sub, f"{where}[{index}]")

    walk(schema, path)
    return bad


def unconstrained_object_paths(model: type[BaseModel]) -> list[str]:
    """Find every unconstrained-object location in a model's JSON schema, incl. $defs."""
    schema = model.model_json_schema()
    bad = _scan_schema(schema, model.__name__)
    for def_name, def_schema in (schema.get("$defs") or {}).items():
        bad.extend(_scan_schema(def_schema, f"$defs.{def_name}"))
    return bad
