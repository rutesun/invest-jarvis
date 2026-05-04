# Feature Spec: Daily Report 인과관계 추론

**Status**: In Progress
**Created**: 2026-04-29
**PRs**: -

---

## Why

Daily report가 단순 요약 수준. "블룸 에너지 계약 체결" → 끝.
"왜 중요한가", "어떤 경로로 주가에 영향 주는가" 없음.
리포트는 키워드 체크리스트일 뿐, 실제 판단은 원문 직접 읽고 내가 함.

## What

1. **Reduce 프롬프트 V3**: impact에 인과관계 체인 (2-3단계, `→` 연결) + `⚡ 투자 시사점` 요구
2. **Wrapup 프롬프트 V3**: 500자 텍스트 덩어리 → 구조화 포맷 (제목 체인 + 본문 + 🎯/⚠️), 300자 이내
3. **Few-shot 예시**: 좋은 체인 3개 + 나쁜 체인 2개
4. **LLM-as-Judge**: 5차원 평가 (chain_presence, chain_validity, actionability, data_grounding, conciseness), 0-10점. V2 baseline 대비 V3 평균 7점 이상 목표
5. **Wrapup 입력 보강**: `summary[:100]` → 전체 summary + impact 전달

## Constraints

- stages에서 `_V2` 직접 import 중 → `_V3`로 변경 필수
- V2 프롬프트에 `{examples}` placeholder 없음 → V3에 추가 필요
- `reduce_examples.py` 이미 존재 → 수정 (생성 아님)
- V3 실패율 20% 초과 시 V2로 자동 롤백

## Checklist

- [x] Reduce/Wrapup 프롬프트 V3 + stages import 변경
- [x] Wrapup 입력 `summary[:100]` → 전체 전달
- [x] Few-shot 예시 추가
- [x] LLM-as-Judge 평가 구현 (기존 `evaluations/` 확장)
- [x] V2 baseline → V3 채점 비교 (V2: 9.0, V3: 9.7, +0.7 개선)
- [ ] 실전 테스트 3-5일
- [ ] `docs/FEATURES.md` 업데이트

## Related

- 상세 설계: `/brainstorming` → `/writing-plans`로 생성
- Codex 리뷰: 2026-04-29 (12개 지적, 주요 5개 반영)
- 현재 프롬프트: Reduce V2 (`prompts.py:350`), Wrapup V2 (`prompts.py:480`)
- 리포트 샘플: `reports/2026-04/daily_2026-04-28.md`
