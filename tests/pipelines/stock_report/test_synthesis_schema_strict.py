"""Regression guard: synthesis output models must yield valid OpenAI *strict* schemas.

Why this exists
---------------
The tiered synthesis path (``synthesize_category`` / ``synthesize_ticker`` /
``synthesize_overview`` in ``src/pipelines/stock_report/synthesize.py``) hands its Pydantic
output models to ``invoke_llm_with_retry`` -> ``llm.with_structured_output(model)``
(``src/pipelines/daily_report/llm_utils.py``).  For the OpenAI provider,
``ChatOpenAI.with_structured_output`` defaults to ``method="json_schema"`` and binds the
Pydantic model directly as ``response_format``; the OpenAI SDK then serializes that model into
a strict JSON schema via ``openai.lib._pydantic.to_strict_json_schema`` before the request is
sent, and the API rejects (HTTP 400) any strict schema that contains a free-form object
(``additionalProperties: true``, from a ``dict[str, Any]`` field) or an untyped node
(``items: {}``, from a ``list[Any]`` field).

In commit 94f55e4 the output models used ``related_stocks: list[dict[str, Any]]`` and
``evidence_chunk_ids: list[Any]``.  Those produced exactly such an invalid strict schema, so
every per-category/ticker/overview synthesis call failed with a 400 and silently fell back to
raw deterministic cards.  The unit tests at the time monkeypatched ``_run_synthesis_call`` and
never exercised the strict-schema conversion boundary, so they passed; the regression was only
caught by a manual live-API run.  These tests close that gap.

Faithfulness / non-tautology
-----------------------------
- ``_build_openai_strict_schema`` runs the *same* serialization the real path triggers
  (``to_strict_json_schema``) and then asserts the OpenAI strict rules the server enforces.
  Verified versions: langchain-core 1.3.0, langchain-openai 1.1.14, openai 2.32.0 — in which
  none of ``to_strict_json_schema`` / ``convert_to_openai_tool(strict=True)`` /
  ``_convert_to_openai_response_format(strict=True)`` raise on the buggy shapes, so a bare
  "does it raise?" check would be a tautology.
- ``langchain_core...convert_to_openai_tool(Model, strict=True)`` is deliberately *not* used:
  it is the function-calling converter (not the json_schema one this path uses) and it
  silently rewrites ``additionalProperties: true`` to ``false``, masking the very bug.
- The negative cases below recreate the pre-94f55e4 shapes and prove the guard fails on them.
"""

from __future__ import annotations

from typing import Any

import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, Field

from src.pipelines.stock_report.synthesize import (
    CategoryCardLLMOutput,
    OverviewCoreThemeOutput,
    OverviewLLMOutput,
    OverviewPulseItemOutput,
    RelatedStockLLM,
    TickerCardLLMOutput,
)


# Models directly passed to invoke_llm_with_retry: CategoryCardLLMOutput, TickerCardLLMOutput,
# OverviewLLMOutput. Nested types (RelatedStockLLM, OverviewPulseItemOutput,
# OverviewCoreThemeOutput) are included for early signal before the parent's $defs traversal.
SYNTHESIS_OUTPUT_MODELS: list[type[BaseModel]] = [
    RelatedStockLLM,
    CategoryCardLLMOutput,
    TickerCardLLMOutput,
    OverviewPulseItemOutput,
    OverviewCoreThemeOutput,
    OverviewLLMOutput,
]


def _assert_strict_schema_node(node: object, path: str = "$") -> None:
    """Raise ``ValueError`` if any node breaks an OpenAI strict structured-output rule.

    Reproduces the two server-side checks the original bug tripped:
    - a ``"type": "object"`` node whose ``additionalProperties`` is not ``False``
      (``dict[str, Any]`` emits ``additionalProperties: true``);
    - an empty/untyped schema node ``{}`` (``list[Any]`` emits ``items: {}``).
    """
    if not isinstance(node, dict):
        return
    if node == {}:
        raise ValueError(f"untyped/empty schema node at {path} (e.g. a list[Any] field)")
    if node.get("type") == "object" and node.get("additionalProperties") is not False:
        raise ValueError(
            f"object at {path} has additionalProperties="
            f"{node.get('additionalProperties')!r}; OpenAI strict mode requires false"
        )
    for key, value in (node.get("properties") or {}).items():
        _assert_strict_schema_node(value, f"{path}.properties.{key}")
    items = node.get("items")
    if isinstance(items, dict):
        _assert_strict_schema_node(items, f"{path}.items")
    for combinator in ("anyOf", "allOf", "oneOf"):
        for index, variant in enumerate(node.get(combinator) or []):
            _assert_strict_schema_node(variant, f"{path}.{combinator}[{index}]")
    for defs_key in ("$defs", "definitions"):
        for name, definition in (node.get(defs_key) or {}).items():
            _assert_strict_schema_node(definition, f"{path}.{defs_key}.{name}")


def _build_openai_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Serialize ``model`` as the real synthesis path does, then strict-validate it.

    ``to_strict_json_schema`` is the OpenAI SDK converter that
    ``ChatOpenAI.with_structured_output(method="json_schema")`` ultimately triggers when it
    binds a Pydantic model as ``response_format``.  It does not reject the buggy shapes itself
    in the installed versions, so ``_assert_strict_schema_node`` adds the strict validation the
    OpenAI API performs server-side.
    """
    schema = to_strict_json_schema(model)
    _assert_strict_schema_node(schema)
    return schema


@pytest.mark.parametrize("model", SYNTHESIS_OUTPUT_MODELS, ids=lambda model: model.__name__)
def test_synthesis_output_model_is_openai_strict_compatible(model: type[BaseModel]) -> None:
    """Each synthesis output model must convert to a valid OpenAI strict schema."""
    schema = _build_openai_strict_schema(model)
    assert schema["type"] == "object"


# --- Negative cases: recreate the pre-94f55e4 shapes so the guard can't be a tautology. ---


class _BrokenDictAnyOutput(BaseModel):
    """Pre-fix ``CategoryCardLLMOutput.related_stocks`` shape (``list[dict[str, Any]]``)."""

    name: str = ""
    related_stocks: list[dict[str, Any]] = Field(default_factory=list)


class _BrokenListAnyOutput(BaseModel):
    """Pre-fix ``evidence_chunk_ids`` / ``source_card_indices`` shape (``list[Any]``)."""

    evidence_chunk_ids: list[Any] = Field(default_factory=list)


def test_dict_any_field_is_rejected_by_strict_guard() -> None:
    """``list[dict[str, Any]]`` emits ``additionalProperties: true`` — the exact 94f55e4 400."""
    with pytest.raises(ValueError, match="additionalProperties"):
        _build_openai_strict_schema(_BrokenDictAnyOutput)


def test_list_any_field_is_rejected_by_strict_guard() -> None:
    """``list[Any]`` emits an untyped ``{}`` item schema, also invalid under strict mode."""
    with pytest.raises(ValueError, match="untyped/empty"):
        _build_openai_strict_schema(_BrokenListAnyOutput)
