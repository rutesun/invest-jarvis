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

## 7) T07 이후: 주간 taxonomy 정제 루프

`T07` 완료 후에는 라운드 튜닝과 별개로 주간 taxonomy 정제 루프를 운영한다.
주간 정제 전이라도 당일 리포트 품질을 보존하기 위해, 실행 중에만 쓰는 `daily runtime taxonomy overlay`를 함께 사용한다.

1. 당일 overlay 생성
- canonical taxonomy에 매칭되지 않은 unit을 당일 기준으로 임시 그룹화한다.
- 임시 값은 `provisional_category`, `provisional_theme`, `is_provisional=true`로 남긴다.
- 리포트 display에는 provisional 값을 사용할 수 있지만, `config/stock_report_vocabulary.yaml`에는 즉시 반영하지 않는다.

2. 후보 수집
- `vocab_candidates` 저장소에 정규화 실패/변환 후보를 누적한다.
- 저장 시 `raw_value -> normalized_value`와 `message_type`, `canonical_summary`를 함께 남긴다.

3. 주간 집계
- 최근 7일 기준으로 후보를 집계해 빈도/채널 다양성/signal 비중으로 정렬한다.
- 결과를 `alias 추가`, `신규 theme`, `무시` 3개 버킷으로 리포팅한다.

4. 사람 승인 반영
- 자동 반영은 금지하고, 검토 후 `config/stock_report_vocabulary.yaml`만 업데이트한다.
- 반영 후 고정 fixture 날짜로 재실행해 `unclassified` 비율과 샘플 품질을 확인한다.
