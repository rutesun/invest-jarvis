# Stock Report V2 Tuning Round Template (Phase 1 / T06)

이 문서는 `daily-v2` 튜닝을 **한 번에 한 축만 변경**하는 방식으로 진행하기 위한 실행 템플릿이다.

## 1) 라운드 원칙

- 고정 fixture 날짜를 유지한다.
- 라운드당 변경 축은 1개만 선택한다.
- 변경 전/후 같은 커맨드로 실행한다.
- 수치 지표 + 샘플 검토를 같이 기록한다.

## 2) 고정 실행 커맨드

```bash
uv run jarvis report daily-v2 2026-05-08 --preview-limit 50
```

필요하면 같은 방식으로 추가 날짜를 반복 실행한다.

## 3) 라운드 종류

1. Normalize 튜닝
- 대상: `config.yaml`
- 키: `short_comment_max_chars`, `group_window_minutes`, `short_comment_channels`

2. Taxonomy 튜닝
- 대상: `config/stock_report_vocabulary.yaml`
- 키: category/theme alias

3. Classify 룰 튜닝
- 대상: `src/pipelines/stock_report/classify.py`
- 키: semantic extraction prompt, structure_type 판단, canonical_summary 품질, taxonomy normalization

## 4) 측정 지표

- `message_type_counts`
- `category_counts`
- `normalized_rows`, `grouped_only_rows`, `skipped_rows`
- `unclassified` 비율
- canonical_summary 계약 위반 수(빈값, placeholder 요약)
- structure_type 분포와 digest 분할 과/소 여부

## 5) 라운드 로그 (복붙 템플릿)

```md
### Round R{N}
- Date: 2026-05-08
- Axis: normalize | taxonomy | classify
- Why: (무엇을 개선하려는지 1문장)

- Change:
  - file: ...
  - key/rule: ...
  - from: ...
  - to: ...

- Command:
  - uv run jarvis report daily-v2 2026-05-08 --preview-limit 50

- Metrics (Before -> After):
  - message_type_counts: ... -> ...
  - category_counts: ... -> ...
  - grouped_only_rows: ... -> ...
  - skipped_rows: ... -> ...
  - unclassified ratio: ... -> ...

- Sample Review (Top 10):
  - 개선된 사례:
  - 악화된 사례:
  - 보류 이슈:

- Decision:
  - keep | rollback
  - next round hypothesis:
```

## 6) 종료 기준

- 2~3 라운드 연속으로 지표 개선폭이 거의 없다.
- `unclassified` 비율이 목표 이하로 내려온다.
- 샘플 검토에서 오분류/과분류가 허용 수준이다.

위 조건을 만족하면 `T07`(chunk + embed_payload write path)로 이동한다.
