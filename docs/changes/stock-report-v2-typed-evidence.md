# Change Record: Stock Report V2 Typed Evidence + QA Warnings

**Status**: In Progress
**Created**: 2026-05-22
**PRs**: -

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

`supporting_facts` 단일 리스트에 사실/수치/논리/리스크가 섞여 추출 품질이 흔들렸고,
코드 합성(`핵심 수치`, `작성자 코멘트`)이 누적되며 경계가 흐려졌습니다.
LLM 의미 판단과 코드 정규화/검증 경계를 분리해 회귀를 줄일 필요가 있었습니다.

## What

1. LLM 출력 계약을 `evidence_items` 중심으로 전환하고, `supporting_facts`는 내부 파생 필드로 유지.
2. `EvidenceItem`/`QAWarning` 모델 추가 및 `knowledge_chunks.evidence_items`, `knowledge_chunks.qa_warnings` 저장.
3. 숫자/메시지타입 품질 경고(`unsupported_numeric`, `missing_metric_candidate`, `long_evidence`, `admin_contradiction` 등) 도입.
4. grouped-only chunk의 fake evidence 제거 (`supporting_facts=[]`, typed evidence도 빈 배열 유지).
5. tuning/viewer 출력에서 evidence를 kind 단위로 가시화.
6. stock_report 회귀 테스트(모델, 분류, DB, migration, 튜닝, viewer) 확장.

## Constraints

- Phase 1은 warning-only 정책: 경고 발생 시 파이프라인을 중단하지 않음.
- 숫자 QA는 regex/정규화 기반이므로 특수 표기에서는 false positive/negative 가능성이 남음.

## Checklist

- [x] 핵심 구현
- [x] 테스트 통과
- [x] `docs/CLI_USAGE.md` 운영 가이드 반영
- [ ] `docs/FEATURES.md` 업데이트

## Runbook

```bash
# V2 실행
uv run jarvis report daily-v2 2026-05-19 --preview-limit 50

# 비교 검증
uv run jarvis report validate 2026-05-19 --mode compare --preview-limit 50

# 샘플 튜닝
uv run python scripts/stock_report_prompt_tuning.py 2026-05-19 --provider openai --model gpt-5.4-mini

# DB 적재 확인
uv run python scripts/stock_report_show_chunks.py 2026-05-19
```

## Related

- 상세 설계: [docs/superpowers/specs/2026-05-21-stock-report-typed-evidence-design.md](/Users/user/.codex/worktrees/1def/invest-jarvis/docs/superpowers/specs/2026-05-21-stock-report-typed-evidence-design.md)
- ADR: 없음
