# Stock Report V2 Typed Evidence Design

**Date**: 2026-05-21  
**Scope**: `src/pipelines/stock_report/` semantic extraction evidence model  
**Status**: Revised after engineering review; ready for implementation planning

## 1. Problem

`stock_report` Phase 1 currently stores LLM extraction evidence as a flat
`supporting_facts: list[str]`.

This made early implementation simple, but the field now carries too many
different meanings:

- factual evidence
- metrics and numeric evidence
- investment thesis
- risk conditions
- regulatory, market, or structural context
- author comments

Because these meanings are collapsed into one string list, the code started
adding case-specific patches:

- generate `핵심 수치: ...` when the LLM misses a number
- prepend `작성자 코멘트: ...` when the first line looks important
- reinterpret `admin` when report disclosure text appears
- add more prompt rules whenever `supporting_facts` becomes too long or too speculative

These patches reduce individual sample failures, but the direction is brittle.
The extraction layer should separate evidence semantics directly, and the
post-processing layer should validate rather than create meaning.

## 2. Decision

Use **Typed Evidence + QA Warning Only**.

The LLM will output typed `evidence_items`. The pipeline will persist typed
evidence to Postgres and keep `supporting_facts` as a derived compatibility
field. QA checks will produce warnings, but Phase 1 will not retry the LLM or
drop units automatically.

Design boundary:

```text
LLM creates meaning
  -> code normalizes structure
  -> code derives compatibility fields
  -> code warns about quality risks
  -> code does not invent investment meaning
```

## 3. Evidence Model

Use `Literal` instead of an Enum for now. The values are structured-output
constraints and DB strings. They do not need enum methods or custom
serialization.

```python
EvidenceKind = Literal[
    "fact",
    "metric",
    "thesis",
    "risk",
    "market_context",
    "author_comment",
]

class EvidenceItem(BaseModel):
    kind: EvidenceKind
    text: str
```

### LLM Output Model

The LLM output model must not include `supporting_facts`.

```python
class SemanticUnitLLMOutput(BaseModel):
    message_type: Literal["signal", "opinion", "data", "admin"]
    event_type: str | None
    category_key: str | None
    main_theme: str | None
    sub_themes: list[str]
    ticker_tags: list[str]
    canonical_summary: str
    evidence_items: list[EvidenceItem]
```

### Normalized/Internal Model

`supporting_facts` is owned by normalization and persistence. It is derived from
typed evidence for compatibility with downstream chunking/report code.

```python
class QAWarning(BaseModel):
    code: str
    detail: str | None = None
    evidence_index: int | None = None

class ClassifiedMessage:
    ...
    raw_message_type: str | None
    evidence_items: list[EvidenceItem]
    supporting_facts: list[str]
    qa_warnings: list[QAWarning]
```

Derived field:

```python
supporting_facts = [item.text for item in evidence_items]
```

Transition precedence:

- If `evidence_items` exists and is non-empty, it is the source of truth.
- If `evidence_items` is absent or empty but legacy `supporting_facts` exists,
  normalization may convert each item to `EvidenceItem(kind="fact", text=item)`.
- If both fields exist, `evidence_items` wins. Legacy `supporting_facts` is
  ignored except for a QA warning in tuning output if values materially diverge.
- After the prompt contract is updated, new tests should prefer `evidence_items`.

## 4. Evidence Kind Semantics

| Kind | Meaning | Example |
|------|---------|---------|
| `fact` | Core factual statement without special numeric or thesis role | `Micron, SanDisk, Western Digital도 동반 하락` |
| `metric` | Number, percentage, amount, valuation, volume, period, growth rate | `Seagate 주가는 8% 이상 하락` |
| `thesis` | Why this matters as an investment narrative | `수요 강세와 공급 제약 구조는 유지된다는 해석` |
| `risk` | Condition that weakens or breaks the thesis | `빅테크가 AI 인프라 투자를 멈추는 것이 핵심 리스크` |
| `market_context` | Non-thesis market background needed to interpret the unit: regulation, market structure, pricing cycle, recovery mechanism, contract condition, or analyst forecast context | `J.P. Morgan은 메모리 가격이 2027년 말까지 높은 수준을 유지할 수 있다고 언급` |
| `author_comment` | Clearly separated author view before the source article/body | `작성자는 이번 하락을 차익실현 명분에 가깝다고 해석` |

Titles, channel names, links, report bylines, and compliance/distribution
footers are not evidence unless they carry investment content.

`market_context` intentionally replaces the narrower `regulatory_context`.
Actual messages more often contain pricing context, industry structure, analyst
forecast background, or contract mechanics than pure legal/regulatory content.
The `market_` prefix keeps the kind broad enough for stock-report evidence while
preventing it from becoming a catch-all bucket for ordinary facts.

## 5. Prompt Contract

The prompt should ask for `evidence_items` as the primary evidence output.

Core rules:

- `evidence_items` must be short, source-grounded evidence.
- Each item must have `kind` and `text`.
- Do not create market impact, beneficiary, or risk statements that are not in
  the source message.
- Use `metric` for explicit numbers, percentages, amounts, periods, valuation
  multiples, and growth rates.
- Use `thesis`, `risk`, and `market_context` only when the source contains those ideas.
- Use `author_comment` only for a clearly separated author interpretation or
  preface, not for titles, links, channel labels, or bylines.
- Do not request or accept `supporting_facts` as a primary LLM field.

### Example: Short Title + Link

Source:

```text
트럼프 “19일 예정 이란 공격 일단 보류”...새 종전안엔 “실망했다”
https://...
```

Expected LLM output:

```yaml
canonical_summary: 트럼프가 이란 공격 보류와 종전안 실망을 언급
evidence_items:
  - kind: fact
    text: 트럼프 “19일 예정 이란 공격 일단 보류”
  - kind: fact
    text: 새 종전안엔 “실망했다”
```

Not expected:

```yaml
evidence_items:
  - kind: thesis
    text: 중동 지정학 리스크가 유가와 위험자산 변동성을 확대할 수 있다
```

The second output invents a synthesis-stage interpretation during extraction.

### Example: Single Topic Deep Message

Source:

```text
그냥 차익실현 핑계죠...
수요 좋다 + 공급 타이트하다 = 변함없고 오히려 피크아웃은 아니다고 봅니다.

[Seagate CEO 발언 이후 메모리·스토리지 관련주 하락]
- Seagate 주가는 8% 이상 하락
- Micron, SanDisk, Western Digital도 동반 하락
- J.P. Morgan은 메모리 가격이 2027년 말까지 높은 수준을 유지할 수 있다고 언급
```

Expected LLM output:

```yaml
canonical_summary: Seagate 발언으로 메모리 피크아웃 우려가 부각
evidence_items:
  - kind: author_comment
    text: 작성자는 이번 하락을 차익실현 명분에 가깝다고 해석
  - kind: thesis
    text: 수요 강세와 공급 제약 구조는 유지된다는 해석
  - kind: metric
    text: Seagate 주가는 8% 이상 하락
  - kind: fact
    text: Micron, SanDisk, Western Digital도 동반 하락
  - kind: market_context
    text: J.P. Morgan은 메모리 가격이 2027년 말까지 높은 수준을 유지할 수 있다고 언급
```

Derived internal projection:

```yaml
supporting_facts:
  - 작성자는 이번 하락을 차익실현 명분에 가깝다고 해석
  - 수요 강세와 공급 제약 구조는 유지된다는 해석
  - Seagate 주가는 8% 이상 하락
  - Micron, SanDisk, Western Digital도 동반 하락
  - J.P. Morgan은 메모리 가격이 2027년 말까지 높은 수준을 유지할 수 있다고 언급
```

## 6. DB Persistence

Add typed evidence and QA warnings to `knowledge_chunks`:

```sql
ALTER TABLE knowledge_chunks
ADD COLUMN IF NOT EXISTS evidence_items JSONB NOT NULL DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS qa_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
ADD CONSTRAINT knowledge_chunks_evidence_items_array
  CHECK (jsonb_typeof(evidence_items) = 'array'),
ADD CONSTRAINT knowledge_chunks_qa_warnings_array
  CHECK (jsonb_typeof(qa_warnings) = 'array');
```

`supporting_facts` remains stored for compatibility.

`evidence_items` JSONB shape:

```json
[
  {"kind": "metric", "text": "Seagate 주가는 8% 이상 하락"},
  {"kind": "market_context", "text": "J.P. Morgan은 메모리 가격이 2027년 말까지 높은 수준을 유지할 수 있다고 언급"}
]
```

`qa_warnings` JSONB shape:

```json
[
  {
    "code": "unsupported_numeric",
    "detail": "Evidence contains numeric token not found in source: 2000억달러",
    "evidence_index": 0
  }
]
```

DB normalization rules:

- Unknown `kind` values are converted to `fact` and emit `unknown_evidence_kind`.
- Empty or whitespace-only `text` values are dropped and emit `empty_evidence`.
- Duplicate evidence texts inside the same unit are deduplicated after trimming.
- Existing rows are not backfilled semantically. They keep `evidence_items=[]`
  and `qa_warnings=[]` until the message is reprocessed.
- Grouped-only chunks that are created without an LLM extraction unit store
  `evidence_items=[]`; their grouping metadata must not be converted into fake
  evidence.

Persistence flow:

```text
LLM output
  -> evidence_items
  -> normalize/validate with source text and raw LLM fields
  -> supporting_facts = evidence_items.text
  -> qa_warnings
  -> knowledge_chunks
```

Viewer and tuning tools should display:

- `evidence_items` grouped by kind
- derived `supporting_facts`
- `qa_warnings` under each unit when present

## 7. QA Warning Design

Phase 1 warnings are diagnostic only. They do not stop the default daily
pipeline, retry the LLM, or drop units.

Warnings should be generated after LLM extraction with access to both raw and
normalized values:

```text
(raw_unit, normalized_unit, source_text) -> qa_warnings
```

This is required because `admin_contradiction` depends on the raw LLM
`message_type=admin` even if normalization later keeps the downstream type
compatible.

Tuning/validation tools should make warnings visible and may fail a focused
validation command when explicitly run with a warning threshold. The default
daily pipeline does not fail on warnings.

Initial warning set:

| Warning | Meaning |
|---------|---------|
| `unsupported_numeric` | Evidence contains a meaningful numeric token not found in the source text |
| `missing_metric_candidate` | Source has important-looking metrics but no `metric` evidence |
| `long_evidence` | Evidence item is too long and likely summarizes or expands too much |
| `admin_contradiction` | Raw LLM output labels a non-notice investment unit as `message_type=admin` |
| `empty_evidence` | Unit has no evidence items after trimming |
| `unknown_evidence_kind` | LLM returned a kind outside the allowed `Literal` values |
| `legacy_facts_diverged` | LLM returned both typed evidence and materially different legacy `supporting_facts` |

### Numeric QA Contract

Numeric QA is not a general hallucination detector. It only guards obvious
numeric mismatches and obvious missing metrics.

Normalize comparable numeric forms:

| Source Form | Evidence Form | Match |
|-------------|---------------|-------|
| `8%` | `8% 이상` | yes |
| `8퍼센트` | `8%` | yes |
| `2,000억` | `2000억` | yes |
| `$2B` | `20억달러` | yes when unit conversion is deterministic |
| `2027년 말` | `2027년 말까지` | yes |

Ignore numeric tokens from noisy contexts:

- index labels: `S&P500`, `NASDAQ100`
- stock codes: `271560.KS`, `005930`, `000660.KS`
- dates and times: `2026-05-19`, `5월 19일`, `07:09`
- phone numbers: `02-3772-2578`
- URLs and attachment IDs
- report page numbers and footer metadata
- Telegram message IDs and channel IDs

`unsupported_numeric` should trigger only when the evidence introduces a
meaningful investment number that cannot be matched to the source after the
normalization and ignore rules above.

`missing_metric_candidate` should trigger only when the source contains
important-looking metrics and the unit has no `metric` evidence at all. It
should not require every number in the source to appear as metric evidence.

### Unsupported Numeric Example

Source:

```text
메타가 루이지애나에 초대형 AI 데이터센터를 건설 중
```

LLM output:

```yaml
evidence_items:
  - kind: metric
    text: 메타가 2000억달러 규모 AI 데이터센터를 건설
```

QA:

```yaml
qa_warnings:
  - code: unsupported_numeric
    detail: "Evidence contains numeric token not found in source: 2000억달러"
    evidence_index: 0
```

The pipeline continues. The tuning report makes the issue visible.

### Admin Contradiction Example

Raw LLM output:

```yaml
structure_type: multi_item_digest
message_type: admin
category_key: 바이오/헬스케어
ticker_tags: [현대바이오]
evidence_items:
  - kind: fact
    text: 현대바이오가 WHO 요청 시 제프티 즉시 공급 준비를 언급
```

QA:

```yaml
qa_warnings:
  - code: admin_contradiction
    detail: "Raw message_type=admin but unit contains investment content"
```

Design invariant:

```text
message_type=admin is valid only for notice-like units.
```

Phase 1 warns first instead of auto-rewriting all admin outputs.

## 8. Post-Processing Responsibility

Post-processing should not create investment meaning.

Remove or disable meaning-creating patches:

- `핵심 수치: ...` synthetic evidence generation
- `작성자 코멘트: ...` synthetic evidence insertion
- broad keyword-based admin rewrites that hide the original contradiction

Post-processing should:

- normalize taxonomy keys
- normalize event type aliases
- derive `supporting_facts` from `evidence_items`
- compute QA warnings from raw unit, normalized unit, and source text
- keep compatibility with downstream chunking

Implementation ownership map:

| Path | Responsibility |
|------|----------------|
| `src/pipelines/stock_report/models.py` | `EvidenceItem`, `QAWarning`, LLM output model, normalized model fields |
| `src/pipelines/stock_report/prompts.py` | LLM contract: request `evidence_items`; do not request `supporting_facts` |
| `src/pipelines/stock_report/classify.py` | Normalize evidence, derive `supporting_facts`, compute QA warnings, keep raw-vs-normalized values |
| `src/pipelines/stock_report/chunking.py` | Pass typed evidence through chunk drafts; keep grouped-only chunks evidence-empty |
| `src/pipelines/stock_report/db.py` | Persist/read JSONB evidence and QA warnings |
| `src/pipelines/stock_report/tuning.py` | Render warning summary and unit-level evidence by kind |
| `scripts/stock_report_show_chunks.py` | Show stored evidence and warnings grouped by message/unit |

## 9. Regression Tests

Regression tests are part of this change, not optional follow-up work.

Add golden cases for the failures already observed:

| Case | Input Pattern | Expected Guard |
|------|---------------|----------------|
| `sp500_map_numeric_noise` | `S&P500 map` with no real numeric metric | No `metric` evidence for `500`; no synthetic `핵심 수치: 500` |
| `orion_report_header` | Report title, stock code, analyst phone, footer disclosure | No `author_comment` from title/byline; not classified as admin solely due to disclosure |
| `seagate_author_thesis` | Author preface followed by Seagate article body | Preserve `author_comment`, `thesis`, `metric`, and `risk` as separate evidence kinds |
| `title_link_no_invented_thesis` | One-line headline plus URL | Do not invent market impact or risk thesis |
| `hyundai_bio_admin_contradiction` | Investment item labeled admin by LLM | Produce `admin_contradiction` warning |
| `unsupported_numeric_warning` | LLM evidence contains source-missing number | Produce `unsupported_numeric` warning |
| `missing_metric_candidate_warning` | Source has obvious metric but no metric evidence | Produce `missing_metric_candidate` warning |
| `legacy_supporting_facts_only` | Legacy LLM/result has only `supporting_facts` | Convert to `EvidenceItem(kind="fact")` |
| `typed_and_legacy_both_present` | LLM/result has both fields | Typed evidence wins; divergent legacy facts emit warning |
| `invalid_evidence_kind` | LLM returns unsupported kind | Convert to `fact` and emit `unknown_evidence_kind` |
| `old_db_row_defaults` | Existing DB row has no typed evidence | Read as empty arrays without crashing |
| `grouped_only_chunk_no_fake_evidence` | Grouped-only chunk generated without LLM unit | Keep `evidence_items=[]`; do not synthesize metadata evidence |
| `llm_fallback_message` | LLM extraction fails and fallback unit is produced | Keep fallback compatible and warning-visible |
| `admin_raw_label_warning_retained` | Raw LLM says `admin`, normalization keeps downstream compatible | Preserve `admin_contradiction` warning |

Focused unit tests should cover:

- Pydantic validation for allowed evidence kinds
- deriving `supporting_facts` from `evidence_items`
- typed evidence precedence over legacy `supporting_facts`
- legacy-only conversion to `EvidenceItem(kind="fact")`
- numeric QA ignore cases for index labels, stock codes, dates, phones, URLs,
  page numbers, and message IDs
- numeric QA match cases for Korean units, percentages, ranges, and deterministic
  currency shorthand
- DB insert payload includes `evidence_items` and `qa_warnings`
- DB read path handles old rows with default empty arrays
- tuning output renders evidence by kind and warnings
- chunk viewer renders typed evidence and warnings
- grouped-only chunks do not create fake typed evidence

Focused real-data validation should use the prompt-tuning runner with picked
messages:

```bash
uv run python scripts/stock_report_prompt_tuning.py 2026-05-19 \
  --data-dir data \
  --sample-size 4 \
  --per-channel 0 \
  --pick Brain_And_Body_Research:112492 \
  --pick jeilstock:44799 \
  --pick jeilstock:44802 \
  --pick shinhanresearch:50923
```

Add Seagate and 현대바이오 samples if present in the same fixture set.

## 10. Implementation Scope

Included:

- Add `EvidenceItem`
- Add `QAWarning`
- Add `evidence_items` and `qa_warnings` to semantic/classified models
- Update LLM prompt contract to use typed evidence
- Derive `supporting_facts` from `evidence_items`
- Add migration for `knowledge_chunks.evidence_items` and `knowledge_chunks.qa_warnings`
- Update DB insert/read paths
- Update tuning report output
- Update DB chunk viewer output
- Add regression tests listed above
- Remove or disable meaning-generating numeric and lead-comment patches

Excluded:

- LLM repair retry
- Unsupported evidence auto-drop
- Final report synthesis rewrite
- Vector DB recall
- PDF/news evidence integration
- Moving event type taxonomy to YAML
- Broad category taxonomy redesign

## 11. Success Criteria

- Existing `stock_report` tests pass.
- New regression tests pass.
- Prompt tuning output shows `evidence_items` grouped by kind.
- `supporting_facts` remains available for existing chunking/report code.
- `knowledge_chunks` persists `evidence_items`, `supporting_facts`, and `qa_warnings`.
- Existing rows and grouped-only chunks remain readable without typed evidence.
- No code path synthesizes `핵심 수치:` or `작성자 코멘트:` as evidence.
- QA warnings make extraction quality issues visible without stopping Phase 1 runs.
- Tuning output includes warning counts by type and unit-level warning details.
