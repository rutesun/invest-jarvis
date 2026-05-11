# Change Record: Structure Zone Reporting 개선

**Status**: In Progress
**Created**: 2026-05-07
**PRs**: -

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

`jarvis analyze`의 구조 레벨 출력이 기계적인 터치 수 중심으로 보이고, 박스권/지지/저항/패턴의 역할 구분이 약했다.
최근 구조보다 오래된 터치 군집이 과하게 노출되거나, 최종 출력에서 사용자가 무엇을 먼저 읽어야 하는지 불명확한 문제가 있었다.

## What

1. 구조 해석 설계를 `zone`과 `pattern` 분리 기준으로 재정리했다.
2. `StructureLevelsPayloadV2` 기준으로 구조 출력 계약을 확장했다.
3. 구조 출력에 `headline/why`, `no_clear_structure`, 우선순위 규칙을 반영했다.
4. `inspect_structure_zone.py`와 inspector 테스트를 추가해 선택 근거를 추적할 수 있게 했다.
5. zone 회귀 테스트와 fixture를 보강해 tuning 비교 기반을 만들었다.

## Constraints

- `docs/FEATURES.md`는 PR 단계에서만 업데이트한다.
- legacy `demand/supply/balance`는 호환 wrapper 내부에만 남기고 새 경로에서는 제거한다.
- 구조 출력 품질은 대표 fixture(`PGY`, `NVTS`, `ALAB`, `066970.KQ`) 회귀 기준으로 검증한다.

## Checklist

- [x] 핵심 구현
- [ ] 테스트 통과
- [ ] `docs/FEATURES.md` 업데이트

## Related

- 상세 설계: `docs/superpowers/specs/2026-05-07-zone-pattern-separation-design.md`
- ADR: `docs/adr/0006-separate-zone-pattern-and-v2-structure-payload.md`
