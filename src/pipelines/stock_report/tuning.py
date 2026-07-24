from __future__ import annotations

import csv
import logging
import random
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from src.llm.stage_config import StageLLMConfig
from src.pipelines.stock_report.classify import classify_messages
from src.pipelines.stock_report.config import get_semantic_extraction_llm_config
from src.pipelines.stock_report.models import (
    ClassifiedMessage,
    EvidenceItem,
    NormalizedMessage,
    RawTelegramMessage,
)
from src.pipelines.stock_report.normalize import normalize_messages
from src.pipelines.stock_report.prompts import SEMANTIC_EXTRACTION_SYSTEM_PROMPT
from src.pipelines.stock_report.taxonomy import load_taxonomy_registry
from src.pipelines.stock_report.telegram_ingest import (
    discover_csv_files,
    parse_channel_key,
    parse_timestamp,
)


logger = logging.getLogger(__name__)


MessageSelector = tuple[str, str]
IMPORTANT_QA_WARNING_CODES: tuple[str, ...] = (
    "unsupported_numeric",
    "missing_metric_candidate",
    "under_split_candidate",
    "over_merged_unit_candidate",
    "duplicate_unit_candidate",
    "empty_evidence",
    "long_evidence",
    "unknown_evidence_kind",
    "legacy_facts_diverged",
)
MAX_QA_SAMPLES_PER_CODE = 3
MAX_TAXONOMY_SAMPLES = 5
MAX_COMPACT_TEXT_CHARS = 100


@dataclass(slots=True)
class PromptTuningRunResult:
    date: str
    provider: str
    model: str | None
    csv_files: int
    parsed_rows: int
    normalized_rows: int
    candidate_rows: int
    sampled_rows: int
    classified_units: int
    system_prompt_source: str
    structure_type_counts: dict[str, int]
    message_type_counts: dict[str, int]
    category_counts: dict[str, int]
    output_markdown: str


def _normalize_nullable_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or normalized.lower() == "null":
        return None
    return normalized


def _load_normalize_config(config_path: str = "config.yaml") -> tuple[set[str], int, int]:
    path = Path(config_path)
    if not path.exists():
        return {"hana_us_stock"}, 100, 30

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    normalize = payload.get("stock_report", {}).get("normalize", {})
    channels = set(normalize.get("short_comment_channels", ["hana_us_stock"]))
    max_chars = int(normalize.get("short_comment_max_chars", 100))
    window = int(normalize.get("group_window_minutes", 30))
    return channels, max_chars, window


def _load_raw_messages_from_csv(date: str, data_dir: str) -> tuple[list[RawTelegramMessage], int]:
    csv_files = discover_csv_files(date=date, data_dir=data_dir)
    parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
    raw_messages: list[RawTelegramMessage] = []
    next_message_id = 1

    for csv_path in csv_files:
        channel_key = parse_channel_key(date=date, csv_path=csv_path)
        with csv_path.open(encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if not row.get("message_id") or not row.get("timestamp"):
                    continue

                posted_at = parse_timestamp(row["timestamp"])
                raw_messages.append(
                    RawTelegramMessage(
                        id=next_message_id,
                        source_date=parsed_date,
                        date_kst=posted_at.date(),
                        posted_at=posted_at,
                        channel_key=channel_key,
                        channel_name=row.get("channel_name") or channel_key,
                        channel_message_id=str(row["message_id"]),
                        author=_normalize_nullable_text(row.get("author")),
                        raw_text=row.get("content") or "",
                        media_info=_normalize_nullable_text(row.get("media_info")),
                        forward_from_channel_key=None,
                        forward_from_channel_name=None,
                    )
                )
                next_message_id += 1

    return raw_messages, len(csv_files)


def select_tuning_samples(
    normalized_messages: list[NormalizedMessage],
    *,
    sample_size: int,
    per_channel: int,
    seed: int,
    include_grouped_only: bool,
    picked_messages: set[MessageSelector] | None = None,
    strict_picks: bool = True,
) -> list[NormalizedMessage]:
    if sample_size <= 0:
        return []

    if include_grouped_only:
        candidates = [
            row
            for row in normalized_messages
            if row.processing_mode != "skip" and row.clean_text.strip()
        ]
    else:
        candidates = [
            row
            for row in normalized_messages
            if row.processing_mode == "full" and row.clean_text.strip()
        ]
    if not candidates:
        return []

    picked_messages = picked_messages or set()
    selected: list[NormalizedMessage] = []
    selected_ids: set[int] = set()

    if picked_messages:
        missing = set(picked_messages)
        for row in sorted(candidates, key=lambda item: (item.posted_at, item.telegram_message_id)):
            selector = (row.channel_key, row.channel_message_id)
            if selector not in picked_messages:
                continue
            selected.append(row)
            selected_ids.add(row.telegram_message_id)
            missing.discard(selector)

        if missing and strict_picks:
            missing_text = ", ".join(
                f"{channel}:{message_id}" for channel, message_id in sorted(missing)
            )
            raise ValueError(f"선택한 메시지를 찾지 못했습니다: {missing_text}")

    effective_sample_size = max(sample_size, len(selected))

    rng = random.Random(seed)
    by_channel: dict[str, list[NormalizedMessage]] = defaultdict(list)
    for row in candidates:
        if row.telegram_message_id in selected_ids:
            continue
        by_channel[row.channel_key].append(row)
    for rows in by_channel.values():
        rng.shuffle(rows)

    channel_keys = sorted(by_channel.keys())

    for channel_key in channel_keys:
        channel_rows = by_channel[channel_key]
        take = max(0, per_channel)
        for row in channel_rows[:take]:
            if row.telegram_message_id in selected_ids:
                continue
            selected.append(row)
            selected_ids.add(row.telegram_message_id)
            if len(selected) >= effective_sample_size:
                break
        if len(selected) >= effective_sample_size:
            break

    if len(selected) < effective_sample_size:
        remaining = [row for row in candidates if row.telegram_message_id not in selected_ids]
        rng.shuffle(remaining)
        needed = effective_sample_size - len(selected)
        selected.extend(remaining[:needed])

    selected.sort(key=lambda row: (row.posted_at, row.telegram_message_id))
    return selected


def _resolve_system_prompt(system_prompt_path: str | None) -> tuple[str, str]:
    if not system_prompt_path:
        return SEMANTIC_EXTRACTION_SYSTEM_PROMPT, "builtin"

    path = Path(system_prompt_path)
    if not path.exists():
        raise FileNotFoundError(f"프롬프트 파일을 찾을 수 없습니다: {path}")
    return path.read_text(encoding="utf-8").strip(), str(path)


def _build_output_markdown(
    *,
    result: PromptTuningRunResult,
    sampled_rows: list[NormalizedMessage],
    classified_rows: list[ClassifiedMessage],
    max_raw_chars: int,
) -> str:
    warning_counts = _count_qa_warnings(classified_rows)
    lines = [
        "# Stock Report V2 Prompt Tuning",
        "",
        f"- date: `{result.date}`",
        f"- provider: `{result.provider}`",
        f"- model: `{result.model or 'default'}`",
        f"- prompt source: `{result.system_prompt_source}`",
        f"- csv files: `{result.csv_files}`",
        f"- parsed rows: `{result.parsed_rows}`",
        f"- normalized rows: `{result.normalized_rows}`",
        f"- candidate rows: `{result.candidate_rows}`",
        f"- sampled rows: `{result.sampled_rows}`",
        f"- classified units: `{result.classified_units}`",
        f"- structure_type counts: `{result.structure_type_counts}`",
        f"- message_type counts: `{result.message_type_counts}`",
        f"- category counts: `{result.category_counts}`",
        "",
    ]
    lines.extend(
        _build_qa_review_section(
            sampled_rows=sampled_rows,
            classified_rows=classified_rows,
            warning_counts=warning_counts,
        )
    )
    lines.extend(
        [
            "",
            "## Sample Outputs",
        ]
    )

    units_by_message_id: dict[int, list[ClassifiedMessage]] = defaultdict(list)
    for unit in classified_rows:
        units_by_message_id[unit.telegram_message_id].append(unit)
    for units in units_by_message_id.values():
        units.sort(key=lambda unit: unit.unit_index)

    for idx, row in enumerate(sampled_rows, start=1):
        units = units_by_message_id.get(row.telegram_message_id, [])
        raw_text = row.raw_text.strip()
        if max_raw_chars > 0 and len(raw_text) > max_raw_chars:
            raw_text = f"{raw_text[:max_raw_chars]} ...[truncated]"

        lines.append("")
        lines.append(
            f"### {idx}. [{row.channel_key}] msg={row.channel_message_id} units={len(units)} "
            f"mode={row.processing_mode}"
        )
        lines.append("```text")
        lines.append(raw_text or "(empty)")
        lines.append("```")

        if not units:
            lines.append("- units: `none`")
            continue

        for unit in units:
            lines.append(
                f"- unit[{unit.unit_index}] `{unit.message_type}` / `{unit.category_key}` / "
                f"`{unit.structure_type}`: {unit.canonical_summary}"
            )
            if unit.event_type:
                lines.append(f"  - event_type: `{unit.event_type}`")
            if unit.main_theme:
                lines.append(f"  - main_theme: `{unit.main_theme}`")
            if unit.sub_themes:
                lines.append(f"  - sub_themes: `{', '.join(unit.sub_themes)}`")
            lines.append(
                "  - provisional: "
                f"`category={unit.provisional_category or '-'}, "
                f"theme={unit.provisional_theme or '-'}, "
                f"is_provisional={unit.is_provisional}`"
            )
            if unit.ticker_tags:
                lines.append(f"  - ticker_tags: `{', '.join(unit.ticker_tags)}`")
            for kind, evidence_texts in _group_evidence_by_kind(unit.evidence_items).items():
                lines.append(f"  - evidence_items.{kind}: `{' | '.join(evidence_texts)}`")
            if unit.supporting_facts:
                lines.append(f"  - supporting_facts: `{' | '.join(unit.supporting_facts)}`")
            if unit.qa_warnings:
                warning_text = " | ".join(
                    (f"{warning.code}: {warning.detail}" if warning.detail else warning.code)
                    for warning in unit.qa_warnings
                )
                lines.append(f"  - qa_warnings: `{warning_text}`")

    return "\n".join(lines)


def _count_qa_warnings(classified_rows: list[ClassifiedMessage]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for unit in classified_rows:
        for warning in unit.qa_warnings:
            counts[warning.code] = counts.get(warning.code, 0) + 1
    return dict(sorted(counts.items()))


def _build_qa_review_section(
    *,
    sampled_rows: list[NormalizedMessage],
    classified_rows: list[ClassifiedMessage],
    warning_counts: dict[str, int],
) -> list[str]:
    lines = [
        "## QA Review",
        f"- warning counts by code: `{warning_counts}`",
    ]
    if not classified_rows:
        lines.append("- warning samples: `none`")
        return lines

    row_by_message_id = {row.telegram_message_id: row for row in sampled_rows}

    for code in IMPORTANT_QA_WARNING_CODES:
        if warning_counts.get(code, 0) <= 0:
            continue
        samples = _collect_warning_samples_for_code(
            code=code,
            classified_rows=classified_rows,
            row_by_message_id=row_by_message_id,
        )
        lines.append("")
        lines.append(f"### warning: {code}")
        for unit, row, warning_detail in samples[:MAX_QA_SAMPLES_PER_CODE]:
            lines.append(
                f"- {_format_unit_compact(unit=unit, row=row)} "
                f"warning={code}: {_compact_text(warning_detail)}"
            )

    unclassified_units = _collect_issue_units(
        classified_rows=classified_rows,
        row_by_message_id=row_by_message_id,
        predicate=lambda unit: unit.category_key == "unclassified",
    )
    if unclassified_units:
        lines.append("")
        lines.append("### taxonomy-gap samples (category_key=unclassified)")
        for unit, row in unclassified_units[:MAX_TAXONOMY_SAMPLES]:
            lines.append(
                f"- {_format_unit_compact(unit=unit, row=row)} "
                f"warnings={_format_warning_summary(unit)}"
            )

    mismatch_units = _collect_issue_units(
        classified_rows=classified_rows,
        row_by_message_id=row_by_message_id,
        predicate=lambda unit: (
            unit.category_key != "unclassified"
            and bool(unit.provisional_category or unit.provisional_theme)
        ),
    )
    if mismatch_units:
        lines.append("")
        lines.append("### category/provisional mismatch samples")
        for unit, row in mismatch_units[:MAX_TAXONOMY_SAMPLES]:
            lines.append(
                f"- {_format_unit_compact(unit=unit, row=row)} "
                f"warnings={_format_warning_summary(unit)}"
            )

    return lines


def _collect_warning_samples_for_code(
    *,
    code: str,
    classified_rows: list[ClassifiedMessage],
    row_by_message_id: dict[int, NormalizedMessage],
) -> list[tuple[ClassifiedMessage, NormalizedMessage | None, str]]:
    samples: list[tuple[ClassifiedMessage, NormalizedMessage | None, str]] = []
    for unit in classified_rows:
        for warning in unit.qa_warnings:
            if warning.code != code:
                continue
            row = row_by_message_id.get(unit.telegram_message_id)
            samples.append((unit, row, warning.detail or "-"))
    samples.sort(key=lambda entry: _unit_sort_key(entry[0], entry[1]))
    return samples


def _collect_issue_units(
    *,
    classified_rows: list[ClassifiedMessage],
    row_by_message_id: dict[int, NormalizedMessage],
    predicate: Callable[[ClassifiedMessage], bool],
) -> list[tuple[ClassifiedMessage, NormalizedMessage | None]]:
    result: list[tuple[ClassifiedMessage, NormalizedMessage | None]] = []
    for unit in classified_rows:
        if not predicate(unit):
            continue
        row = row_by_message_id.get(unit.telegram_message_id)
        result.append((unit, row))
    result.sort(key=lambda entry: _unit_sort_key(entry[0], entry[1]))
    return result


def _unit_sort_key(
    unit: ClassifiedMessage, row: NormalizedMessage | None
) -> tuple[str, str, int, str]:
    channel_key = row.channel_key if row else unit.channel_key
    channel_message_id = row.channel_message_id if row else "-"
    return (
        channel_key,
        channel_message_id,
        unit.unit_index,
        _compact_text(unit.canonical_summary),
    )


def _format_unit_compact(*, unit: ClassifiedMessage, row: NormalizedMessage | None) -> str:
    channel_key = row.channel_key if row else unit.channel_key
    channel_message_id = row.channel_message_id if row else "-"
    return (
        f"[{channel_key}#{channel_message_id}] "
        f"unit={unit.unit_index} "
        f"cat={unit.category_key} "
        f"main={unit.main_theme or '-'} "
        f"prov_cat={unit.provisional_category or '-'} "
        f"prov_theme={unit.provisional_theme or '-'} "
        f"is_prov={unit.is_provisional} "
        f"summary={_compact_text(unit.canonical_summary)}"
    )


def _format_warning_summary(unit: ClassifiedMessage) -> str:
    if not unit.qa_warnings:
        return "-"
    parts = [
        (f"{warning.code}: {_compact_text(warning.detail)}" if warning.detail else warning.code)
        for warning in unit.qa_warnings
    ]
    return " | ".join(parts)


def _compact_text(text: str | None, *, max_chars: int = MAX_COMPACT_TEXT_CHARS) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= max_chars:
        return normalized
    if max_chars <= 3:
        return normalized[:max_chars]
    return f"{normalized[: max_chars - 3]}..."


def _group_evidence_by_kind(evidence_items: list[EvidenceItem]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in evidence_items:
        grouped.setdefault(item.kind, []).append(item.text)
    return grouped


def run_prompt_tuning_round(
    *,
    date: str,
    data_dir: str = "data",
    llm_config: StageLLMConfig | None = None,
    config_path: str = "config.yaml",
    taxonomy_path: str = "config/stock_report_vocabulary.yaml",
    sample_size: int = 24,
    per_channel: int = 2,
    seed: int = 7,
    include_grouped_only: bool = False,
    picked_messages: set[MessageSelector] | None = None,
    strict_picks: bool = True,
    system_prompt_path: str | None = None,
    max_raw_chars: int = 6000,
) -> PromptTuningRunResult:
    started_at = time.perf_counter()
    llm_config = llm_config or get_semantic_extraction_llm_config()
    logger.info(
        "prompt tuning started: date=%s provider=%s model=%s sample_size=%d per_channel=%d picks=%d",
        date,
        llm_config.provider,
        llm_config.model,
        sample_size,
        per_channel,
        len(picked_messages or set()),
    )
    raw_messages, csv_file_count = _load_raw_messages_from_csv(date=date, data_dir=data_dir)
    logger.info(
        "prompt tuning csv loaded: files=%d parsed_rows=%d", csv_file_count, len(raw_messages)
    )
    short_channels, max_chars, group_window = _load_normalize_config(config_path)
    normalized_rows = normalize_messages(
        raw_messages,
        short_comment_channels=short_channels,
        short_comment_max_chars=max_chars,
        group_window_minutes=group_window,
    )
    logger.info("prompt tuning normalization completed: normalized_rows=%d", len(normalized_rows))
    sampled_rows = select_tuning_samples(
        normalized_rows,
        sample_size=sample_size,
        per_channel=per_channel,
        seed=seed,
        include_grouped_only=include_grouped_only,
        picked_messages=picked_messages,
        strict_picks=strict_picks,
    )
    logger.info("prompt tuning sampling completed: sampled_rows=%d", len(sampled_rows))

    system_prompt, prompt_source = _resolve_system_prompt(system_prompt_path)
    logger.info("prompt tuning prompt resolved: source=%s", prompt_source)
    taxonomy = load_taxonomy_registry(taxonomy_path)
    classified_rows = classify_messages(
        sampled_rows,
        taxonomy=taxonomy,
        llm_config=llm_config,
        system_prompt=system_prompt,
    )
    logger.info("prompt tuning classification completed: classified_units=%d", len(classified_rows))

    structure_type_counts: dict[str, int] = {}
    message_type_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for unit in classified_rows:
        structure_type_counts[unit.structure_type] = (
            structure_type_counts.get(unit.structure_type, 0) + 1
        )
        message_type_counts[unit.message_type] = message_type_counts.get(unit.message_type, 0) + 1
        category_counts[unit.category_key] = category_counts.get(unit.category_key, 0) + 1

    candidate_rows = sum(
        1
        for row in normalized_rows
        if row.clean_text.strip() and (include_grouped_only or row.processing_mode == "full")
    )

    result = PromptTuningRunResult(
        date=date,
        provider=llm_config.provider,
        model=llm_config.model,
        csv_files=csv_file_count,
        parsed_rows=len(raw_messages),
        normalized_rows=len(normalized_rows),
        candidate_rows=candidate_rows,
        sampled_rows=len(sampled_rows),
        classified_units=len(classified_rows),
        system_prompt_source=prompt_source,
        structure_type_counts=structure_type_counts,
        message_type_counts=message_type_counts,
        category_counts=category_counts,
        output_markdown="",
    )
    result.output_markdown = _build_output_markdown(
        result=result,
        sampled_rows=sampled_rows,
        classified_rows=classified_rows,
        max_raw_chars=max_raw_chars,
    )
    logger.info(
        "prompt tuning completed: sampled_rows=%d classified_units=%d elapsed=%.2fs",
        result.sampled_rows,
        result.classified_units,
        time.perf_counter() - started_at,
    )
    return result


def write_prompt_tuning_report(result: PromptTuningRunResult, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.output_markdown, encoding="utf-8")
    return path
