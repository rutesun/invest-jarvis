# Stock Report V2 Typed Evidence Design

**Date**: 2026-05-21  
**Scope**: `src/pipelines/stock_report/` semantic extraction evidence model  
**Status**: Design approved for implementation planning

## 1. Problem

`stock_report` Phase 1 currently stores LLM extraction evidence as a flat
`supporting_facts: list[str]`.

This made early implementation simple, but it is now carrying too many meanings:

- factual evidence
- metrics and numeric evidence
- investment thesis
- risk conditions
- regulatory or pricing context
- author comments

Because these are all collapsed into one string list, the code started adding
case-specific patches:

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

## 3. Evidence Model

Add an `EvidenceItem` model:

```python
EvidenceKind = Literal[
    "fact",
    "metric",
    "thesis",
    "risk",
    "regulatory_context",
    "author_comment",
]

class EvidenceItem(BaseModel):
    kind: EvidenceKind
    text: str
```

Use `Literal` instead of an Enum for now. The kind values are simple structured
output constraints and DB strings. They do not need enum methods or custom
serialization.

Update the extraction models:

```python
class SemanticUnitDraft(BaseModel):
    message_type: Literal["signal", "opinion", "data", "admin"]
    event_type: str | None
    category_key: str | None
    main_theme: str | None
    sub_themes: list[str]
    ticker_tags: list[str]
    canonical_summary: str
    evidence_items: list[EvidenceItem]
    supporting_facts: list[str]  # derived compatibility field
```

Update the normalized classified model similarly:

```python
class ClassifiedMessage:
    ...
    evidence_items: list[EvidenceItem]
    supporting_facts: list[str]
    qa_warnings: list[str]
```

`supporting_facts` is derived from typed evidence:

```python
supporting_facts = [item.text for item in evidence_items]
```

If the LLM returns legacy `supporting_facts` during a transition period,
normalization may convert each item to `EvidenceItem(kind="fact", text=item)`.
After the prompt contract is updated, tests should prefer `evidence_items`.

## 4. Evidence Kind Semantics

| Kind | Meaning | Example |
|------|---------|---------|
| `fact` | Core factual statement without special numeric or thesis role | `Micron, SanDisk, Western Digital도 동반 하락` |
| `metric` | Number, percentage, amount, valuation, volume, period, growth rate | `Seagate 주가는 8% 이상 하락` |
| `thesis` | Why this matters as an investment narrative | `수요 강세와 공급 제약 구조는 유지된다는 해석` |
| `risk` | Condition that weakens or breaks the thesis | `빅테크가 AI 인프라 투자를 멈추는 것이 핵심 리스크` |
| `regulatory_context` | Institutional, regulatory, pricing, or recovery mechanism context | `FERC/PJM 가격 통제가 유틸리티 수익성 변수` |
| `author_comment` | Clearly separated author view before the source article/body | `작성자는 이번 하락을 차익실현 명분에 가깝다고 해석` |

Titles, channel names, links, report bylines, and compliance/distribution
footers are not evidence unless they carry investment content.

## 5. Prompt Contract

The prompt should ask for `evidence_items` as the primary evidence output.

Core rules:

- `evidence_items` must be short, source-grounded evidence.
- Each item must have `kind` and `text`.
- Do not create market impact, beneficiary, or risk statements that are not in
  the source message.
- Use `metric` for explicit numbers, percentages, amounts, periods, valuation
  multiples, and growth rates.
- Use `thesis`, `risk`, and `regulatory_context` only when the source contains
  those ideas.
- Use `author_comment` only for a clearly separated author interpretation or
  preface, not for titles, links, channel labels, or bylines.
- `supporting_facts` should not be requested as a primary LLM field.

### Example: Short Title + Link

Source:

```text
트럼프 “19일 예정 이란 공격 일단 보류”...새 종전안엔 “실망했다”
https://...
```

Expected:

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

Expected:

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
  - kind: regulatory_context
    text: J.P. Morgan은 메모리 가격이 2027년 말까지 높은 수준을 유지할 수 있다고 언급
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
ADD COLUMN evidence_items JSONB NOT NULL DEFAULT '[]'::jsonb,
ADD COLUMN qa_warnings JSONB NOT NULL DEFAULT '[]'::jsonb;
```

`supporting_facts` remains stored for compatibility.

Persistence flow:

```text
LLM output
  -> evidence_items
  -> normalize/validate
  -> supporting_facts = evidence_items.text
  -> qa_warnings
  -> knowledge_chunks
```

Viewer and tuning tools should display:

- `evidence_items` grouped by kind
- derived `supporting_facts`
- `qa_warnings` under each unit when present

## 7. QA Warning Design

Phase 1 warnings are diagnostic only. They do not stop the pipeline, retry the
LLM, or drop units.

Initial warning set:

| Warning | Meaning |
|---------|---------|
| `unsupported_numeric` | Evidence contains a numeric token not found in the source text |
| `missing_metric_candidate` | Source has important-looking metrics but no `metric` evidence |
| `long_evidence` | Evidence item is too long and likely summarizes or expands too much |
| `admin_contradiction` | A non-notice investment unit is labeled `message_type=admin` |
| `empty_evidence` | Unit has no evidence items |

Warnings should be generated after LLM extraction and normalization.

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
  - unsupported_numeric
```

The pipeline continues. The tuning report makes the issue visible.

### Admin Contradiction Example

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
  - admin_contradiction
```

Design invariant:

```text
message_type=admin is valid only for notice-like units.
```

Phase 1 will warn first instead of auto-rewriting all admin outputs.

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
- compute QA warnings
- keep compatibility with downstream chunking

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

Focused unit tests should cover:

- Pydantic validation for allowed evidence kinds
- deriving `supporting_facts` from `evidence_items`
- DB insert payload includes `evidence_items` and `qa_warnings`
- tuning output renders evidence by kind and warnings
- chunk viewer renders typed evidence and warnings

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
- No code path synthesizes `핵심 수치:` or `작성자 코멘트:` as evidence.
- QA warnings make extraction quality issues visible without stopping Phase 1 runs.

