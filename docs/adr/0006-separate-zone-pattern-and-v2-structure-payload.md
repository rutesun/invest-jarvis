# ADR-0006: Zone/Pattern 분리와 StructureLevelsPayloadV2 도입

**상태:** 수락
**날짜:** 2026-05-07

## 컨텍스트

`jarvis analyze`의 구조 해석은 그동안 `수요/공급 zone`과 `차트 패턴`이 섞여 있어, 사람이 읽을 때 `지금 중요한 박스권인지`, `오래된 패턴 참고인지`, `현재 구조가 애매한지`를 빠르게 판단하기 어려웠다.

특히 다음 문제가 반복됐다.

- 최근 박스권과 오래된 터치 군집이 같은 레벨 후보로 섞인다.
- `W`, `triangle` 같은 시간 분산 패턴과 현재 구조 레벨이 서로 다른 언어로 설명된다.
- 최종 출력에서 `demand/supply/balance`와 실행 레벨이 함께 섞여 사용자 판단 우선순위가 흐려진다.

이번 변경에서는 구조 탐지 엔진 경계와 외부 출력 계약을 함께 정리해야 했다.

## 고려한 옵션

### 옵션 A: 기존 unified structure detector 유지
- 장점:
  - 파일 변경이 가장 적다.
  - 기존 테스트와 출력 형식을 크게 건드리지 않아도 된다.
- 단점:
  - 박스권, 지지/저항, 형상 패턴의 책임 경계가 계속 섞인다.
  - `PGY`, `NVTS` 같은 차트에서 최근 구조와 오래된 패턴을 분리해 설명하기 어렵다.

### 옵션 B: `SwingExtractor`를 공유하고 `Zone Engine`과 `Pattern Engine`을 분리
- 장점:
  - 박스/지지/저항과 형상 패턴의 책임을 분명히 나눌 수 있다.
  - 구조 출력 우선순위와 패턴 표시 우선순위를 별도로 튜닝할 수 있다.
  - inspector와 회귀 테스트에서 선택 근거를 더 명확히 추적할 수 있다.
- 단점:
  - 출력 계약과 호환 레이어를 함께 정리해야 한다.
  - 초기 구현 범위가 단순 리포트 문구 수정보다 커진다.

### 옵션 C: 엔진은 유지하고 최종 리포트 문구만 개선
- 장점:
  - 사용자 체감 문구는 빠르게 좋아질 수 있다.
  - 내부 구조 리스크가 적다.
- 단점:
  - 잘못된 구조 후보를 더 예쁘게 설명하는 수준에 그칠 수 있다.
  - zone/pattern 충돌과 stale structure 문제를 근본적으로 해결하지 못한다.

## 결정

옵션 B를 채택한다.

구체적으로는 아래를 함께 채택한다.

1. 구조 해석은 `Zone Engine`, 형상 해석은 `Pattern Engine`이 담당한다.
2. 두 엔진은 공통 `SwingExtractor` 결과를 사용하되, pattern 쪽은 raw OHLC 문맥이 필요하므로 `df + swings` 계약을 유지한다.
3. 외부 소비 계약은 `StructureLevelsPayloadV2`로 통일한다.
4. `demand/supply/balance`는 legacy wrapper 내부 호환에만 남기고 새 경로에서는 사용하지 않는다.
5. 구조 점수가 임계치에 못 미치면 억지로 레벨을 만들지 않고 `no_clear_structure`를 허용한다.
6. 최종 출력은 `현재 가장 중요한 구조 / headline / why`를 먼저 보여주고, 그 아래에 structure block과 pattern block을 분리한다.

## 결과

- 구조 레벨과 차트 패턴의 튜닝 포인트가 분리된다.
- `level_composer -> deep_dive -> llm/analyzer -> CLI` 경로는 `StructureLevelsPayloadV2`만 소비한다.
- 최종 사용자는 첫 3줄 안에서 현재 구조를 빠르게 읽을 수 있게 된다.
- inspector와 회귀 테스트는 `touch episode`, `selection priority`, `legacy vs v2 diff`를 기준으로 비교할 수 있다.
- 반대급부로 migration 중에는 legacy wrapper, golden output, shadow mode 테스트를 함께 관리해야 한다.
