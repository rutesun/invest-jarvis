# Change Record: Daily Report 인과관계 추론 (Reduce/Wrapup V3)

**Status**: In Progress
**Date**: 2026-04-29
**PRs**: -
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

Daily report가 단순 요약 수준에 머물렀다. "블룸 에너지 계약 체결" → 끝. "왜 중요한가",
"어떤 경로로 주가에 영향 주는가"가 없어서 리포트는 키워드 체크리스트였고, 실제 판단은
원문 직접 읽고 내가 하는 구조였다. LLM-as-Judge로 V2 baseline을 채점한 결과 9.0점 —
인과관계 부재(`chain_presence`)가 주요 감점 요인임을 확인했다.

## What

1. **Reduce 프롬프트 V3**: impact에 인과관계 체인(2-3단계, `→` 연결) + `⚡ 투자 시사점`
   요구를 추가했다. "계약 체결 → 수주 잔고 확대 → 2027 매출 상향 가능" 형태가 목표 출력.
   few-shot에 좋은 체인 3개 + 나쁜 체인 2개를 추가했고, 나쁜 예시는 단순 나열형과 비인과
   연결형으로 구분했다.

2. **Wrapup 프롬프트 V3**: 500자 텍스트 덩어리 방식을 버리고 `제목 체인 + 본문 + 🎯/⚠️`
   구조화 포맷으로 전환했다. 300자 이내 제약 추가. V2는 Wrapup 입력으로 `summary[:100]`만
   전달했는데, impact 없이 summary만 보면 체인 추론이 불가능해서 전체 summary + impact를
   전달하도록 바꿨다.

3. **LLM-as-Judge 5차원 평가**: `chain_presence`(인과 체인 있음/없음), `chain_validity`
   (논리적 인과인가), `actionability`(투자 행동 연결), `data_grounding`(수치 근거),
   `conciseness`(300자 이내)를 0-10점으로 채점. 기존 `evaluations/` 구조를 확장했다.
   V2 baseline 9.0 → V3 9.7, +0.7 개선 확인.

## Before / After

```
Before (Reduce V2):
  "블룸 에너지, 데이터센터 전력 공급 계약 체결"

After (Reduce V3):
  "블룸 에너지, 데이터센터 전력 공급 계약 체결
   → 수주 잔고 확대 → 2027 매출 상향 가능
   ⚡ 투자 시사점: AI 전력 테마 추세 수혜, 단기 모멘텀 확인 후 접근"
```

```
Before (Wrapup V2):
  입력: summary[:100]만 전달
  출력: 500자 텍스트 덩어리

After (Wrapup V3):
  입력: 전체 summary + impact 전달
  출력: 제목 체인 + 본문(300자 이내) + 🎯/⚠️ 구조
```

## Impact

리포트의 각 항목에 `→` 인과 체인과 `⚡ 투자 시사점`이 추가된다. Wrapup 섹션은 300자
이내 구조화 포맷으로 바뀐다. LLM-as-Judge 기준 V2 대비 +0.7점(9.0→9.7) 개선 확인.
실전 테스트 3-5일 후 반영 여부 확정.

## Constraints

- V3 실패율 20% 초과 시 V2 자동 롤백 경로를 유지한다. 프롬프트 변경이 모든 입력 분포에서
  안정적이라는 보장이 없다.
- `stages.py`가 `_V2` suffix를 직접 import하고 있어 `_V3`로 변경 필수. `reduce_examples.py`는
  신규 생성이 아니라 기존 파일 수정.
- 실전 테스트 3-5일 데이터 확인 후 PR 생성. 단일 날짜 eval만으로는 날짜 분포 편향이 있다.

## Related

- 설계: `docs/superpowers/plans/2026-04-29-wrapup-v3-causal-reasoning.md`
- ADR: 없음
- FEATURES.md: 머지 후 업데이트
- 후속: 실전 테스트 → PR 생성
