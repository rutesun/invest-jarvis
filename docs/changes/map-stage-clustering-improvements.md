# Change Record: Map Stage 클러스터링 개선

**Status**: In Progress
**Date**: 2026-04-30
**PRs**: -
**Type**: fix

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

Map stage의 avg_sources가 1.5-1.6 수준으로 목표(1.7-2.0)에 미달했다. temperature 실험
(0.0: 1.34, 0.2: 1.57, 0.3: 1.45)에서 0.0이 오히려 최저를 기록했는데, temperature 0일 때
LLM이 "확신 없으면 분리" 전략을 취해 93%가 1:1 매핑이 되었기 때문이다. 동시에 카테고리
검증 오류(예: `의료/제약` → `바이오/제약`)로 배치마다 2-3개 청크가 유실되고 있었다.

## What

1. **temperature 0.2로 고정**: 3회 반복 실험에서 0.2가 avg_sources 1.57로 최고이고
   변동폭(1.52-1.62)이 0.3(1.4-1.5)보다 좁다. `MAP_LLM` config에 반영. temperature 0은
   "공격적 클러스터링" 프롬프트 지침을 사실상 무시하는 결과가 나와 제외.

2. **카테고리 alias 후처리 매핑**: LLM이 허용 카테고리 enum 밖의 표현을 쓸 때(예: `운송`→
   `운송/물류`, `엔터테인먼트`→`엔터/미디어`) retry 3회 후 청크 전체를 버리던 구조를
   `CATEGORY_ALIASES` 사전 매핑으로 교체. 100% 검증 성공 + retry 비용 제거.
   fuzzy matching은 예측 불가 매핑이 발생할 수 있어 alias 사전 방식을 선택했다.

3. **few-shot 예시 재구성**: Good 예시의 avg_sources(3.0-4.0)와 실제 LLM 출력(1.5)의
   격차가 커 LLM이 따라하기 어려운 구조였다. 쉬움(2.0) → 보통(3.5) → 어려움(7.0) 점진적
   난이도 + 도메인 다양화(반도체 편중 → 금융/에너지 추가)로 재편. 나쁜 예시도 과도 분절형 +
   억지 통합형 두 가지로 보강.

## Before / After

```
Before (temperature):
  MAP_LLM = StageLLMConfig(temperature=0.0)
  → avg_sources 1.34, 93% 1:1 매핑

After:
  MAP_LLM = StageLLMConfig(temperature=0.2)
  → avg_sources 1.57, 1:1 매핑 비율 감소
```

```
Before (카테고리 검증):
  LLM → "의료/제약" → ValidationError → retry 3회 → 청크 버림

After:
  LLM → "의료/제약" → CATEGORY_ALIASES → "바이오/제약" → 검증 통과
```

## Impact

사용자 가시 변화는 없으나, 배치마다 유실되던 2-3개 청크가 보존된다. avg_sources가
1.5에서 1.6-1.7 수준으로 개선되어 이슈 통합 품질이 높아진다.

## Constraints

- **Shuffle stage 통합 미구현**: avg_sources 근본 해결책은 Shuffle에서 정규화된 테마 기준으로
  이슈를 재통합하는 것이지만(예상 1.5→2.5+), Reduce/Wrapup 하위 호환성 영향이 크다.
  별도 설계 후 Phase 3로 분리했다.
- **후처리 통합 레이어(Post-Map Merge) 미구현**: 청크 간 유사도로 Map이 놓친 통합 기회를
  포착하는 아이디어가 있었으나 embedding 모델 추가 의존성과 "억지 통합" 리스크로 보류.
- **avg_sources 개선 폭 한계**: 위 3가지로 1.5 → 1.6-1.7이 목표. 1.8-2.0은 Shuffle 통합
  없이는 어렵다.

## Related

- 분석 상세: 10가지 개선 옵션과 temperature 실험 원본은 별도 분석 문서로 보관
  (`docs/superpowers/specs/` 이전 예정)
- ADR: 없음
- FEATURES.md: 해당 없음 (사용자 가시 기능 변화 없음)
- 후속: Phase 3 Shuffle stage 통합 설계
