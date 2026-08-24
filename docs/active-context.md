# Active Context

- **갱신**: 2026-08-24 17:15
- **Branch**: feature/bottom-watch-signal
- **진행 단계**: bottom_watch 검증 실패 → 바닥 사례 귀납 수집으로 전환

## 지금까지
- check 로직을 엘앤에프·실리콘투 as-of 백테스트로 점검 → 하락추세에서 divergence/과매도 바닥 신호가 집계(supertrend/minervini 음수)에 눌려 avoid로 나오는 구조 확인.
- bottom_watch(역추세 바닥 관찰 플래그) 설계 → 독립 리뷰 2건 → 편향 없는 표본(§6) 검증 → **과적합 확인, 구현 보류**.
- 파생 아이디어 ROADMAP 이관: Task 13 저항 인식 패널티(근거 확실), Task 14 구조 점수(higher-low, 보류).

## 핵심 결정
- bottom_watch 트리거 폐기(worklog Pivot). 신호를 먼저 정의하지 않고, 바닥 사례를 다수 수집해 공통 패턴을 귀납 추출하는 순서로 전환.

## 다음 행동
- 사용자로부터 "좋았던 바닥 매수" 사례 10개+ (티커 + 대략 날짜) 수집.
- 각 사례 시점의 지표 상태를 뽑아 공통 패턴 분석 → 신호 정의 후 편향 없는 표본으로 재검증.
