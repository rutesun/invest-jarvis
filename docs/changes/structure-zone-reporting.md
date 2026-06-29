# Change Record: Structure Zone Reporting 개선

**Status**: In Progress
**Date**: 2026-05-07
**PRs**: -
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

`jarvis analyze`의 구조 레벨 출력이 터치 수 중심의 기계적 나열이었다. 박스권/지지/저항/패턴의
역할 구분이 없어서 오래된 터치 군집이 최근 구조보다 과하게 노출되거나, 여러 레벨이 동등하게
나열되어 사용자가 무엇을 먼저 읽어야 하는지 불명확했다. zone(가격대 군집)과 pattern(형태
인식)이 같은 출력 레이어에 섞이는 것이 근본 원인이었다.

## What

1. **zone과 pattern 분리 (`StructureLevelsPayloadV2`)**: zone은 가격대 군집(터치 횟수·강도),
   pattern은 형태 기반 인식(VCP, head-and-shoulders 등)으로 계약을 분리했다. 두 개념이
   같은 `levels` 리스트에 섞이면 각 레벨의 역할을 코드가 구분할 수 없었다. (→ ADR-0006)

2. **`headline/why` 필드 추가**: 가장 중요한 구조 레벨 하나를 `headline`으로 선택하고
   `why`에 선택 근거를 붙이는 방식으로 출력 우선순위를 명시화했다. "무엇을 먼저 읽어야 하나"
   문제를 LLM 자유 텍스트가 아닌 구조 계약 레벨에서 해결.

3. **`no_clear_structure` 플래그**: 구조가 불명확한 종목에서 억지로 레벨을 채워 노이즈가
   생기는 문제를 방지하기 위해 "구조 없음" 상태를 명시적으로 반환할 수 있게 했다.

4. **`inspect_structure_zone.py` + inspector 테스트**: 레벨 선택 근거를 추적 가능하게
   만드는 inspector를 추가했다. tuning 비교 시 레벨이 바뀐 이유를 역추적할 수 있다.
   대표 fixture `PGY`, `NVTS`, `ALAB`, `066970.KQ` 기준으로 zone 회귀 테스트 보강.

## Before / After

```
Before:
  구조 분석:
    [저항] 142.5 (터치 4회)
    [지지] 138.2 (터치 3회)
    [저항] 140.0 (터치 2회)   ← zone/pattern 구분 없이 나열
    (무엇을 먼저 봐야 하는지 불명확)

After:
  구조 분석:
    📌 핵심: 142.5 저항 (터치 4회, 최근 2회 고점 일치 — 돌파 시 목표 148)
    Zone: 138.2 지지 | 140.0 중간 저항
    Pattern: 없음 (no_clear_structure=False)
```

```
Before (StructureLevelsPayload):
  levels: list[Level]  # zone + pattern 혼재

After (StructureLevelsPayloadV2):
  zones: list[Zone]
  patterns: list[Pattern]
  headline: Level
  why: str
  no_clear_structure: bool
```

## Impact

`jarvis analyze` 구조 섹션에서 가장 중요한 레벨이 `headline`으로 먼저 표시되고
선택 이유(`why`)가 함께 나온다. zone과 pattern이 별도 섹션으로 분리된다.
구조가 불명확한 종목은 `no_clear_structure` 플래그로 "구조 없음"이 명시된다.

## Constraints

- `legacy demand/supply/balance` 필드는 호환 wrapper 내부에만 남긴다. 새 경로에서는
  제거. 하위 호환을 위해 wrapper를 한 사이클 더 유지하되, 새 코드가 이를 참조하면 안 된다.
- 구조 출력 품질 검증은 4개 대표 fixture 기준으로만 한다. 전 종목 시뮬레이션은 비용 대비
  효과가 낮아 제외.

## Related

- 설계: `docs/superpowers/specs/2026-05-07-zone-pattern-separation-design.md`,
  `docs/superpowers/specs/2026-05-06-structure-zone-level-design.md`
- ADR: `docs/adr/0006-separate-zone-pattern-and-v2-structure-payload.md`
- FEATURES.md: 머지 후 업데이트
