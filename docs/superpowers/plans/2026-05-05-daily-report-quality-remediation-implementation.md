# Daily Report Quality Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep information coverage high while improving report quality by adding fragment/evidence/rank layers and switching output to `Daily Brief / Extended Themes / Broker Pulse` without changing CLI command options.

**Architecture:** Keep the current daily-report pipeline boundaries, but change internal contracts from `message -> issue` to `fragment -> mapped_event -> merged_cluster -> scored_theme -> rendered_item`. Exclude `wrapup` from the initial remediation scope and enforce stage-gate reviews before moving to the next phase. Preserve the existing `uv run jarvis report daily <date> [--notion]` command contract and change only output structure/content quality.

**Tech Stack:** Python 3.12, pydantic, pytest, Typer, notion-client, existing LLM adapters (OpenAI/Anthropic)

---

## Scope Check

This is one subsystem (`src/pipelines/daily_report/`) with tightly coupled runtime contracts. One integrated plan is appropriate, but each task below is independently testable and has a hard review gate.

## File Map

### Create

- `src/pipelines/daily_report/source_parsing.py`
- `src/pipelines/daily_report/evidence.py`
- `src/pipelines/daily_report/stages/global_merge_stage.py`
- `src/pipelines/daily_report/stages/rank_stage.py`
- `tests/pipelines/daily_report/test_source_parsing.py`
- `tests/pipelines/daily_report/test_evidence.py`
- `tests/pipelines/daily_report/test_global_merge.py`
- `tests/pipelines/daily_report/test_rank_stage.py`
- `tests/pipelines/daily_report/fixtures/golden/2026-04-27/final_report_assertions.json`
- `tests/pipelines/daily_report/fixtures/golden/2026-04-28/final_report_assertions.json`
- `tests/pipelines/daily_report/fixtures/golden/2026-04-29/final_report_assertions.json`
- `tests/pipelines/daily_report/fixtures/golden/2026-04-30/final_report_assertions.json`
- `tests/pipelines/daily_report/fixtures/golden/2026-05-04/final_report_assertions.json`

### Modify

- `src/pipelines/daily_report/models.py`
- `src/pipelines/daily_report/stages/ingest_stage.py`
- `src/pipelines/daily_report/stages/map_stage.py`
- `src/pipelines/daily_report/stages/shuffle_stage.py`
- `src/pipelines/daily_report/stages/reduce_stage.py`
- `src/pipelines/daily_report/pipeline.py`
- `src/pipelines/daily_report/prompts.py`
- `src/cli/main.py`
- `src/integrations/notion.py`
- `scripts/test_daily_report_stages.sh`
- `tests/pipelines/daily_report/test_ingest_stage.py`
- `tests/pipelines/daily_report/test_map_stage.py`
- `tests/pipelines/test_daily_report_pipeline.py`
- `docs/CLI_USAGE.md`
- `README.md`
- `AGENTS.md`

## Stage Gate Rules (Mandatory)

- Gate progression: `Gate 1 (Map)` -> `Gate 2 (Global Merge)` -> `Gate 3 (Rank/Select)` -> `Gate 4 (Reduce/Render/CLI+Notion)`.
- No next-task work starts before current gate check passes.
- Each gate must include:
  1. Focused automated tests PASS
  2. Stage command output artifact generated
  3. Human checklist PASS (quality assertions)

## Task 1: Model Contract + Macro Hygiene Baseline

**Files:**
- Modify: `src/pipelines/daily_report/models.py`
- Modify: `tests/pipelines/daily_report/test_models.py`
- Modify: `tests/pipelines/daily_report/test_ingest_stage.py`

- [ ] **Step 1: Write failing tests for nullable macro + layered report fields**

```python
def test_macro_snapshot_keeps_none_values():
    snap = MacroSnapshot(
        date="2026-05-04",
        us_markets={"S&P500": None},
        kr_markets={"KOSPI": None},
        vix=None,
        fear_greed=None,
        krw_usd=None,
        missing_fields=["vix", "krw_usd"],
    )
    assert snap.vix is None
    assert "vix" in snap.missing_fields


def test_daily_report_has_three_layers():
    report = DailyReport(
        date="2026-05-04",
        macro=MacroSnapshot(
            date="2026-05-04",
            us_markets={"S&P500": 1.0},
            kr_markets={"KOSPI": 0.3},
            vix=18.0,
            fear_greed=55,
            krw_usd=1370.0,
        ),
        brief_items=[],
        extended_items=[],
        broker_pulse_items=[],
    )
    assert report.brief_items == []
```

- [ ] **Step 2: Run focused tests and confirm FAIL**

Run: `uv run pytest tests/pipelines/daily_report/test_models.py tests/pipelines/daily_report/test_ingest_stage.py -q`  
Expected: missing fields / validation errors for new model contracts

- [ ] **Step 3: Implement minimal model changes**

```python
class MacroSnapshot(BaseModel):
    date: str
    us_markets: dict[str, float | None]
    kr_markets: dict[str, float | None]
    vix: float | None = None
    fear_greed: int | None = Field(default=None, ge=0, le=100)
    krw_usd: float | None = None
    missing_fields: list[str] = Field(default_factory=list)


class DailyReport(BaseModel):
    date: str
    macro: MacroSnapshot
    brief_items: list[NewsItem] = Field(default_factory=list)
    extended_items: list[NewsItem] = Field(default_factory=list)
    broker_pulse_items: list[NewsItem] = Field(default_factory=list)
```

- [ ] **Step 4: Re-run focused tests and confirm PASS**

Run: `uv run pytest tests/pipelines/daily_report/test_models.py tests/pipelines/daily_report/test_ingest_stage.py -q`  
Expected: all selected tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/daily_report/models.py tests/pipelines/daily_report/test_models.py tests/pipelines/daily_report/test_ingest_stage.py
git commit -m "refactor: baseline daily report model contracts"
```

## Task 2: Fragment Split + Source Classification

**Files:**
- Create: `src/pipelines/daily_report/source_parsing.py`
- Create: `src/pipelines/daily_report/evidence.py`
- Create: `tests/pipelines/daily_report/test_source_parsing.py`
- Create: `tests/pipelines/daily_report/test_evidence.py`
- Modify: `src/pipelines/daily_report/stages/ingest_stage.py`

- [ ] **Step 1: Add failing parser/classifier tests**

```python
def test_split_shinhanresearch_bundle_row():
    fragments = split_message_into_fragments(
        raw_message_id="shinhanresearch-100",
        channel_id="shinhanresearch",
        text="▶️ A 기사\n내용1\n▶️ B 기사\n내용2",
    )
    assert len(fragments) == 2
    assert fragments[0].fragment_index == 0


def test_classify_broker_summary():
    source_type = classify_source_type(
        channel_id="shinhanresearch",
        title="아침 시황 브리프",
        body="전일 마감 요약",
    )
    assert source_type.value == "broker_summary"
```

- [ ] **Step 2: Run parser/classifier tests and confirm FAIL**

Run: `uv run pytest tests/pipelines/daily_report/test_source_parsing.py tests/pipelines/daily_report/test_evidence.py -q`  
Expected: ImportError for missing parser/classifier functions

- [ ] **Step 3: Implement parser/classifier modules**

```python
def split_message_into_fragments(raw_message_id: str, channel_id: str, text: str) -> list[ArticleFragment]:
    # 1) split by ▶️ / bullet / url boundaries
    # 2) keep fragment_index ordering
    # 3) fallback to single fragment when no delimiter
    ...


def classify_source_type(channel_id: str, title: str, body: str) -> SourceType:
    if "research" in channel_id:
        return SourceType.BROKER_SUMMARY
    if "속보" in title or "Reuters" in body:
        return SourceType.PRIMARY_NEWS
    return SourceType.UNKNOWN
```

- [ ] **Step 4: Wire ingest output to preserve row identity metadata**

```python
messages.append(
    TelegramMessage(
        channel_id=channel_id,
        message_id=row["message_id"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        text=row["content"],
        row_index=row_index,
        source_file=str(csv_file),
    )
)
```

- [ ] **Step 5: Re-run tests and confirm PASS**

Run: `uv run pytest tests/pipelines/daily_report/test_source_parsing.py tests/pipelines/daily_report/test_evidence.py tests/pipelines/daily_report/test_ingest_stage.py -q`

- [ ] **Step 6: Commit**

```bash
git add src/pipelines/daily_report/source_parsing.py src/pipelines/daily_report/evidence.py src/pipelines/daily_report/stages/ingest_stage.py tests/pipelines/daily_report/test_source_parsing.py tests/pipelines/daily_report/test_evidence.py tests/pipelines/daily_report/test_ingest_stage.py
git commit -m "feat: add fragment parsing and source classification"
```

## Task 3: Map Contract Refactor + Gate 1 Review

**Files:**
- Modify: `src/pipelines/daily_report/stages/map_stage.py`
- Modify: `src/pipelines/daily_report/prompts.py`
- Modify: `tests/pipelines/daily_report/test_map_stage.py`
- Modify: `scripts/test_daily_report_stages.sh`

- [ ] **Step 1: Add failing tests for `MappedEvent` contract**

```python
def test_map_outputs_fact_vs_interpretation_fields():
    events = map_stage(messages=[...], date="2026-04-28")
    assert events[0].summary_fact
    assert events[0].summary_interpretation is not None
    assert events[0].source_fragment_ids
```

- [ ] **Step 2: Run map tests and confirm FAIL**

Run: `uv run pytest tests/pipelines/daily_report/test_map_stage.py -q`  
Expected: attribute errors for missing `MappedEvent` fields

- [ ] **Step 3: Implement map output type + prompt constraints**

```python
class MappedEvent(BaseModel):
    category: IssueCategory
    entities: list[str]
    event_type: str
    stance: Sentiment
    keywords: list[str]
    source_fragment_ids: list[str]
    confidence: float
    summary_fact: str
    summary_interpretation: str
```

- [ ] **Step 4: Add Gate 1 stage command path to script**

```bash
uv run python -m src.pipelines.daily_report.stages.ingest_stage "$DATE"
uv run python -m src.pipelines.daily_report.stages.map_stage "$DATE"
```

- [ ] **Step 5: Gate 1 review (must pass before next task)**

Run:

```bash
./scripts/test_daily_report_stages.sh 2026-04-28
jq '. | length' tests/pipelines/daily_report/fixtures/stage_outputs/map_2026-04-28.json
```

Checklist:
- bundled row splits into expected fragment counts
- source mapping is not pinned to first row sentence only
- obvious sector misclassification rate is acceptable

- [ ] **Step 6: Commit**

```bash
git add src/pipelines/daily_report/stages/map_stage.py src/pipelines/daily_report/prompts.py tests/pipelines/daily_report/test_map_stage.py scripts/test_daily_report_stages.sh
git commit -m "refactor: map stage emits fragment-based events"
```

## Task 4: Global Merge Stage + Gate 2 Review

**Files:**
- Create: `src/pipelines/daily_report/stages/global_merge_stage.py`
- Modify: `src/pipelines/daily_report/models.py`
- Modify: `src/pipelines/daily_report/pipeline.py`
- Create: `tests/pipelines/daily_report/test_global_merge.py`

- [ ] **Step 1: Add failing tests for cross-chunk dedupe**

```python
def test_global_merge_collapses_same_event_across_chunks():
    merged = global_merge_stage(events=[event_a1, event_a2, event_a3], date="2026-04-29")
    assert len(merged) == 1
    assert merged[0].independent_evidence_count == 1
```

- [ ] **Step 2: Run global merge tests and confirm FAIL**

Run: `uv run pytest tests/pipelines/daily_report/test_global_merge.py -q`

- [ ] **Step 3: Implement merge stage and pipeline insertion**

```python
def run_pipeline(date: str, data_dir: str = "data") -> DailyReport:
    ingest_result = ingest(date, data_dir)
    mapped_events = map_stage(ingest_result.messages, date)
    merged_clusters = global_merge_stage(mapped_events, date)
    shuffled = shuffle_stage(merged_clusters, date)
    ...
```

- [ ] **Step 4: Re-run tests and confirm PASS**

Run: `uv run pytest tests/pipelines/daily_report/test_global_merge.py tests/pipelines/daily_report/test_map_stage.py -q`

- [ ] **Step 5: Gate 2 review (must pass before next task)**

Run:

```bash
uv run python -m src.pipelines.daily_report.stages.global_merge_stage 2026-04-29
jq '. | map(.independent_evidence_count) | add' tests/pipelines/daily_report/fixtures/stage_outputs/global_merge_2026-04-29.json
```

Checklist:
- repeated summaries of same event become one cluster
- unrelated events do not over-merge
- dedupe works across map chunk boundaries

- [ ] **Step 6: Commit**

```bash
git add src/pipelines/daily_report/stages/global_merge_stage.py src/pipelines/daily_report/models.py src/pipelines/daily_report/pipeline.py tests/pipelines/daily_report/test_global_merge.py
git commit -m "feat: add global merge evidence clustering stage"
```

## Task 5: Rank/Select Stage + Gate 3 Review

**Files:**
- Create: `src/pipelines/daily_report/stages/rank_stage.py`
- Modify: `src/pipelines/daily_report/models.py`
- Modify: `src/pipelines/daily_report/pipeline.py`
- Create: `tests/pipelines/daily_report/test_rank_stage.py`
- Modify: `scripts/test_daily_report_stages.sh`

- [ ] **Step 1: Add failing tests for layer allocation**

```python
def test_rank_stage_demotes_broker_only_to_watchlist():
    scored = rank_stage(theme_clusters=[broker_only_theme], date="2026-05-04")
    assert scored.watchlist_candidates
    assert not scored.brief_candidates


def test_rank_stage_keeps_coverage_in_extended():
    scored = rank_stage(theme_clusters=mixed_themes, date="2026-05-04")
    assert len(scored.extended_candidates) >= 1
```

- [ ] **Step 2: Run rank tests and confirm FAIL**

Run: `uv run pytest tests/pipelines/daily_report/test_rank_stage.py -q`

- [ ] **Step 3: Implement rank scoring policy**

```python
score = (
    independent_evidence_count * 0.35
    + source_diversity * 0.20
    + primary_source_bonus
    - broker_summary_penalty
    - single_source_penalty
    + market_signal_bonus
    + cross_category_link_bonus
    - speculative_penalty
)
```

- [ ] **Step 4: Re-run tests and confirm PASS**

Run: `uv run pytest tests/pipelines/daily_report/test_rank_stage.py tests/pipelines/daily_report/test_global_merge.py -q`

- [ ] **Step 5: Gate 3 review (must pass before next task)**

Run:

```bash
uv run python -m src.pipelines.daily_report.stages.rank_stage 2026-05-04
jq '{brief: (.brief_candidates|length), extended: (.extended_candidates|length), watch: (.watchlist_candidates|length)}' tests/pipelines/daily_report/fixtures/stage_outputs/rank_2026-05-04.json
```

Checklist:
- digest-only/single-source themes are demoted to watchlist
- brief card count stays within policy range
- extended section preserves coverage

- [ ] **Step 6: Commit**

```bash
git add src/pipelines/daily_report/stages/rank_stage.py src/pipelines/daily_report/models.py src/pipelines/daily_report/pipeline.py tests/pipelines/daily_report/test_rank_stage.py scripts/test_daily_report_stages.sh
git commit -m "feat: add rank and layer selection stage"
```

## Task 6: Reduce/Render/CLI/Notion Output Contract + Gate 4 Review

**Files:**
- Modify: `src/pipelines/daily_report/stages/reduce_stage.py`
- Modify: `src/pipelines/daily_report/pipeline.py`
- Modify: `src/cli/main.py`
- Modify: `src/integrations/notion.py`
- Modify: `tests/pipelines/test_daily_report_pipeline.py`

- [ ] **Step 1: Add failing rendering tests for new section structure**

```python
def test_report_structure_has_three_layers(sample_report):
    md = format_report(sample_report)
    assert "## Daily Brief" in md
    assert "## Extended Themes" in md
    assert "## Broker Pulse" in md
    assert "## 💡 Key Insights" not in md
```

- [ ] **Step 2: Run rendering/notion tests and confirm FAIL**

Run: `uv run pytest tests/pipelines/test_daily_report_pipeline.py tests/pipelines/daily_report/test_wrapup_stage.py -q`

- [ ] **Step 3: Implement output contract (no wrapup call in initial scope)**

```python
def run_pipeline(date: str, data_dir: str = "data") -> DailyReport:
    ...
    reduced = reduce_stage(selected_layers, ingest_result.macro, date)
    return DailyReport(
        date=date,
        macro=ingest_result.macro,
        brief_items=reduced.brief_items,
        extended_items=reduced.extended_items,
        broker_pulse_items=reduced.broker_pulse_items,
    )
```

- [ ] **Step 4: Implement Notion toggle behavior for Extended/Broker**

```python
children.append(_heading2("Extended Themes"))
children.extend([_toggle(item.investment_theme, _build_theme_children(item)) for item in report.extended_items])
children.append(_heading2("Broker Pulse"))
children.extend([_toggle(item.investment_theme, _build_theme_children(item)) for item in report.broker_pulse_items])
```

- [ ] **Step 5: Re-run tests and confirm PASS**

Run: `uv run pytest tests/pipelines/test_daily_report_pipeline.py tests/pipelines/daily_report -q`

- [ ] **Step 6: Gate 4 review (must pass before final regression task)**

Run:

```bash
uv run jarvis report daily 2026-05-04
rg -n \"UNKNOWN|PRIVATE|KRW/USD: 0\\.0\" reports/2026-05/daily_2026-05-04.md
```

Checklist:
- single-source item tone is conservative
- no `UNKNOWN` / `PRIVATE` / `0.0` leakage
- Notion block tree shows `Extended Themes` title always visible and item detail toggle-only

- [ ] **Step 7: Commit**

```bash
git add src/pipelines/daily_report/stages/reduce_stage.py src/pipelines/daily_report/pipeline.py src/cli/main.py src/integrations/notion.py tests/pipelines/test_daily_report_pipeline.py
git commit -m "feat: switch daily report output to brief-extended-broker layers"
```

## Task 7: Golden Regression + Manual Replay + Docs Sync

**Files:**
- Create: `tests/pipelines/daily_report/fixtures/golden/*/final_report_assertions.json`
- Modify: `scripts/test_daily_report_stages.sh`
- Modify: `docs/CLI_USAGE.md`
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add failing golden assertion tests for target dates**

```python
@pytest.mark.parametrize("date", ["2026-04-27", "2026-04-28", "2026-04-29", "2026-04-30", "2026-05-04"])
def test_daily_report_golden_assertions(date):
    report = run_pipeline(date)
    assert 10 <= len(report.brief_items) <= 25
    assert not any("UNKNOWN" in item.investment_theme for item in report.brief_items)
```

- [ ] **Step 2: Run golden tests and confirm FAIL**

Run: `uv run pytest tests/pipelines/daily_report -k golden -q`

- [ ] **Step 3: Add golden assertion files and stage replay script updates**

```bash
./scripts/test_daily_report_stages.sh 2026-04-27
./scripts/test_daily_report_stages.sh 2026-04-28
./scripts/test_daily_report_stages.sh 2026-04-29
./scripts/test_daily_report_stages.sh 2026-04-30
./scripts/test_daily_report_stages.sh 2026-05-04
```

- [ ] **Step 4: Re-run full daily-report test suite and confirm PASS**

Run: `uv run pytest tests/pipelines/daily_report tests/pipelines/test_daily_report_pipeline.py -q`  
Expected: all tests PASS

- [ ] **Step 5: Update user-facing docs in same commit**

```markdown
# docs/CLI_USAGE.md
- `uv run jarvis report daily <date> [--notion]` 출력 섹션: Macro Snapshot / Daily Brief / Extended Themes / Broker Pulse
```

- [ ] **Step 6: Commit**

```bash
git add tests/pipelines/daily_report/fixtures/golden scripts/test_daily_report_stages.sh tests/pipelines/daily_report docs/CLI_USAGE.md README.md AGENTS.md
git commit -m "test: lock daily report quality gates and golden regressions"
```

## Final Verification Checklist (Before PR)

- [ ] `uv run pytest tests/pipelines/daily_report tests/pipelines/test_daily_report_pipeline.py -q`
- [ ] `./scripts/test_daily_report_stages.sh 2026-04-28`
- [ ] `./scripts/test_daily_report_stages.sh 2026-05-04`
- [ ] `uv run jarvis report daily 2026-05-04`
- [ ] Manual output review confirms gate criteria for 4 stages

## Self-Review

### 1. Spec Coverage

- Fragment split/source classify: Task 2
- Map contract (fact/interpretation split): Task 3
- Global merge dedupe: Task 4
- Rank/select layering: Task 5
- Brief/Extended/Broker output + Notion toggle: Task 6
- Date-based golden regression + manual stage replay: Task 7
- Wrapup excluded in initial remediation: Task 6 pipeline contract

### 2. Placeholder Scan

- No `TBD`, `TODO`, or "implement later" wording used.
- Every task has explicit files, commands, and pass/fail expectations.

### 3. Type Consistency

- Runtime sequence used consistently: `TelegramMessage -> ArticleFragment -> MappedEvent -> MergedCluster -> ScoredTheme -> NewsItem`.
- Output layers consistently named: `brief_items`, `extended_items`, `broker_pulse_items`.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-05-daily-report-quality-remediation-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
