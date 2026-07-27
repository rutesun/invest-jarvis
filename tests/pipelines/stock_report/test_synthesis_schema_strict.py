"""Regression guard: synthesis LLM output schemas stay OpenAI strict-compatible.

Background (commit 94f55e4)
---------------------------
The per-category / per-ticker / overview synthesis models had a
``related_stocks: dict[str, Any]`` field.  A ``dict[str, Any]`` serializes to a
propertyless ``{"type": "object"}`` (``additionalProperties`` not ``false``),
which OpenAI strict structured-output rejects with HTTP 400
("Invalid schema: needs additionalProperties=false").  Every synthesis call
therefore failed silently and fell back to raw deterministic cards.  The whole
suite missed it because every synthesis test mocks ``_run_synthesis_call`` and
never exercises real schema generation.

Why a schema walk instead of the conversion path
-------------------------------------------------
The obvious guard — call ``convert_to_openai_tool(Model, strict=True)`` (or build
``with_structured_output(..., method="json_schema", strict=True)``) and assert it
does not raise — does NOT work: with the installed langchain-core / langchain-openai
/ openai versions those client-side converters are lenient and do NOT raise on a
``dict[str, Any]`` field; the 400 is produced server-side.  Such a test would pass
on the buggy model too, giving false confidence.  So this guard reproduces the
rule OpenAI enforces server-side: every object schema must declare ``properties``
and ``additionalProperties: false``.  It walks each model's JSON schema (including
``$defs``) and fails fast on any unconstrained object — the exact bug shape.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, Field

import src.pipelines.stock_report.synthesize as synthesize_module
from src.pipelines.stock_report.synthesize import (
    CategoryCardLLMOutput,
    OverviewCoreThemeOutput,
    OverviewLLMOutput,
    OverviewPulseItemOutput,
    RelatedStockLLM,
    TickerCardLLMOutput,
)
from tests.harness.strict_schema import unconstrained_object_paths


# The LLM structured-output models guarded here.  A bare ``from`` import above
# already fails at collection time if any of these is renamed or removed, which
# is itself part of the guard.
#
# Top-level schema targets (passed directly to _run_synthesis_call):
#   CategoryCardLLMOutput, TickerCardLLMOutput, OverviewLLMOutput
#
# Nested-only models (never passed directly to _run_synthesis_call, but their
# schema shape is inlined into the containing model's JSON schema, so an
# unconstrained field here corrupts the top-level schema just as badly):
#   RelatedStockLLM       — nested inside CategoryCardLLMOutput.related_stocks
#   OverviewPulseItemOutput, OverviewCoreThemeOutput — nested inside OverviewLLMOutput
NAMED_SYNTHESIS_OUTPUT_MODELS: tuple[type[BaseModel], ...] = (
    CategoryCardLLMOutput,
    TickerCardLLMOutput,
    OverviewLLMOutput,
    OverviewPulseItemOutput,
    OverviewCoreThemeOutput,
    RelatedStockLLM,
)


def _discover_output_models() -> set[type[BaseModel]]:
    """All Pydantic models *defined in* synthesize.py (its structured-output schemas)."""
    return {
        obj
        for obj in vars(synthesize_module).values()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj is not BaseModel
        and obj.__module__ == synthesize_module.__name__
    }


@pytest.mark.parametrize("model", NAMED_SYNTHESIS_OUTPUT_MODELS, ids=lambda m: m.__name__)
def test_synthesis_output_model_is_strict_compatible(model: type[BaseModel]) -> None:
    """No synthesis output model may contain a dict[str, Any]-style open object."""
    bad = unconstrained_object_paths(model)
    assert not bad, (
        f"{model.__name__} has unconstrained object field(s) at {bad}. OpenAI strict "
        "structured-output rejects these with HTTP 400 (regression of commit 94f55e4); "
        "synthesis would silently fall back to raw cards. Replace dict[str, Any] with a "
        "nested Pydantic model and use typed list items."
    )


def test_guard_covers_every_synthesis_output_model() -> None:
    """The guard list must track the module: catch renamed/removed and new models.

    Without this, a model renamed on another branch (or a newly added output model)
    would slip past the parametrized check above unnoticed.

    Note: nested-only models (RelatedStockLLM, OverviewPulseItemOutput,
    OverviewCoreThemeOutput) are deliberately included even though they are not
    direct _run_synthesis_call targets.  An unconstrained field in a nested model
    is inlined into the containing model's generated JSON schema and causes the same
    HTTP 400 at OpenAI's side.  Over-covering here is safe; under-covering is not.
    """
    discovered = _discover_output_models()
    named = set(NAMED_SYNTHESIS_OUTPUT_MODELS)

    missing = named - discovered
    assert not missing, (
        "guarded models no longer defined in synthesize.py "
        f"(renamed/moved?): {sorted(m.__name__ for m in missing)}"
    )

    unguarded = discovered - named
    assert not unguarded, (
        "new Pydantic model(s) in synthesize.py are not covered by the strict-schema "
        f"guard: {sorted(m.__name__ for m in unguarded)}. Add them to "
        "NAMED_SYNTHESIS_OUTPUT_MODELS."
    )


class _RegressionBugCard(BaseModel):
    """Replicates the pre-94f55e4 schema: related_stocks typed as list[dict[str, Any]]."""

    title: str = ""
    related_stocks: list[dict[str, Any]] = Field(default_factory=list)
    evidence_chunk_ids: list[int] = Field(default_factory=list)


def test_detector_catches_the_original_bug_shape() -> None:
    """Self-check: the detector must flag the exact 94f55e4 bug, or the guard is toothless."""
    flagged = unconstrained_object_paths(_RegressionBugCard)
    assert any("related_stocks" in path for path in flagged), (
        f"detector failed to flag a dict[str, Any] field; flagged={flagged}"
    )


class _BrokenListAnyCard(BaseModel):
    """Replicates the pre-94f55e4 schema: evidence_chunk_ids typed as list[Any]."""

    evidence_chunk_ids: list[Any] = Field(default_factory=list)


def test_detector_catches_list_any_bug_shape() -> None:
    """Self-check: the detector must also flag list[Any] fields (items: {} schema)."""
    flagged = unconstrained_object_paths(_BrokenListAnyCard)
    assert any("evidence_chunk_ids" in path for path in flagged), (
        f"detector failed to flag a list[Any] field; flagged={flagged}"
    )
