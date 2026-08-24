# bottom_watch 신호 설계

> 작성일: 2026-08-24
> 상태: 설계 확정 (구현 대기)
> 관련 보류 항목: [ROADMAP.md] 저항 인식 패널티, 구조 점수(higher-low)

## 배경

현재 기술 스코어링은 추세 확인형(Minervini Stage 2, Supertrend)이라 하락추세가 무너졌다 되살아나는 국면에서 **바닥을 구조적으로 못 잡는다**. 엘앤에프·실리콘투 백테스트에서 divergence(다이버전스)와 cRSI 과매도 훅이 바닥을 정확히 짚었으나, aggregator가 divergence(+35)를 supertrend(-25)·minervini(-20)의 음수와 동등 합산해 최종 판정을 avoid로 눌렀다.

이 재료(바닥 신호)를 판정 action은 건드리지 않고 **별도 관찰 플래그**로 표면화하는 것이 목표다.

### 백테스트 근거 (as-of 재현)

| 종목 | 날짜 | 가격 | 당시 action | 성격 |
|------|------|------|-------------|------|
| 엘앤에프 | 7/31 | 73,300 | avoid | 참 양성 (바닥, 이후 121,600) |
| 엘앤에프 | 7/10 | 100,500 | reduce | **가짜 양성** (이후 65,600까지 -35%) |
| 실리콘투 | 6/29 | 32,650 | reduce | 참 양성 (바닥 6/26=30,400) |

divergence 컴포넌트는 "가격 신저점 + cRSI 저점 상승"(=강세 다이버전스 정의)을 이미 인코딩하므로, cRSI higher-low 재확인은 중복이다. 순수 가격 higher-low 확인은 바닥 당일엔 존재할 수 없어(정의상 바닥 뒤 형성) 같은 시점 가산 시 참/가짜가 역전됐다 → **구조 점수화는 보류**(ROADMAP).

## 설계

### 노출 방식 — 별도 플래그 병기

`action`/`adjusted_score`/`new_entry_allowed`는 **불변**. 기존 스윙 로직·테스트 무손상. `TechnicalVerdict`에 관찰 정보만 추가한다.

```python
class TechnicalVerdict(BaseModel):
    ...
    bottom_watch: bool = False
    bottom_watch_reason: str | None = None
```

의미: "지금은 추세상 회피(avoid/reduce)지만, 강한 역추세 바닥 클러스터가 포착됨. 분할·소액 탐색을 고려하되 직전 저점 이탈 손절 전제." **buy 승격이 아니다** — 백테스트상 조기 신호의 약 절반은 실패(엘앤에프 7/10)하며 손절로 방어하는 성격.

### 트리거 조건 — 윈도우 결합

```
bottom_watch = (
    context.is_downtrend
    AND divergence_component_score >= 35          # 삼중 다이버전스 (가격/MACD/cRSI)
    AND context.recent_oversold_hook              # 최근 15거래일 내 (cRSI<30 & cRSI Hook Up)
)
```

윈도우 결합 근거: 과매도 훅과 다이버전스 클러스터가 같은 날 동시에 뜨지 않고 시점이 어긋나는 경우가 있다(실리콘투: 훅 6/10 ↔ 다이버전스 6/29, 약 13거래일 간격). 10일 윈도우는 실리콘투를 놓치고 20일은 엘앤에프 오탐만 늘려 **15거래일**이 최적이었다.

**튜닝 가능 파라미터 (상수로 분리):**
- `BOTTOM_WATCH_HOOK_LOOKBACK = 15` (거래일)
- `BOTTOM_WATCH_OVERSOLD_CRSI = 30`
- `BOTTOM_WATCH_MIN_DIVERGENCE = 35`

### 아키텍처 — 윈도우 계산은 context, 판정은 aggregator

aggregator는 하루치 `components`+`context`만 받는 무상태 구조라 15일 룩백을 직접 못 본다. `build_market_context(df)`는 df에 접근하므로 **여기서 윈도우를 계산해 `MarketContext`에 불리언을 주입**하고, aggregator는 그 필드만 읽는다. → aggregator 무상태 유지, 관심사 분리.

- `MarketContext`에 `recent_oversold_hook: bool` 추가
  - `build_market_context`에서 cRSI 컬럼을 스캔해 최근 15거래일 중 (cRSI<30 AND 그날 cRSI Hook Up) 발생 여부 계산
  - cRSI Hook Up 판정은 `analyze_crsi`의 훅 로직과 동일 정의를 재사용(공통 헬퍼로 추출)해 최신 바뿐 아니라 과거 바에도 적용
- `divergence_component_score`는 aggregator가 이미 받는 `components["divergence"]["score"]`에서 직접 확인
- `is_downtrend`는 기존 `MarketContext` 필드 활용

플래그 세팅 위치: `ScoreAggregator.aggregate()` 말미에서 verdict 생성 시 계산해 주입. 기존 조정 규칙(cap/override) 흐름은 건드리지 않는다.

### 클리어링 — 무상태 일별 재계산

플래그는 매일 재계산되는 무상태 값이다. 추세가 확인되면 `is_downtrend`가 False가 되어 자연히 꺼진다(엘앤에프 8/14 이후). 별도 만료·지속 상태를 두지 않는다.

### 출력

- **formatter**: `bottom_watch=True`면 판정 아래 한 줄 병기
  예: `⚠ 역추세 바닥 관찰: 삼중 다이버전스 + 최근 과매도 훅 (분할 탐색, 손절=직전 저점)`
- **ScoreHistoryPoint**: `bottom_watch: bool` 추가해 날짜별 추적 가능

## 테스트 (골든)

외부 API raw 응답을 `tests/fixtures/`에 저장하고 as-of 재현으로 검증:

- 엘앤에프 7/31 → `bottom_watch == True`
- 실리콘투 6/29 → `bottom_watch == True`
- 엘앤에프 8/14 (추세 확인 후) → `bottom_watch == False`
- **가짜 양성 케이스** 엘앤에프 7/10 → `bottom_watch == True` (의도된 동작). 테스트 주석에 "조기 신호이며 이후 하락, 손절 전제임"을 명시해 박제.

action/adjusted_score가 기존과 동일하게 유지되는지(회귀) 검증하는 테스트도 포함한다.

## 스코프에서 제외 (ROADMAP으로 이관)

- **저항 인식 패널티**: 슈퍼트렌드 하락전환 직전 주요 고점(예: 실리콘투 4/24=50,500)이 risk 컴포넌트의 최근 스윙 고점 5개(`tail(5)`)에 안 들어가 스코어링에서 안 보임. 미돌파 저항 밑에선 점수를 낮추고 돌파 시 가산하는 개선.
- **구조 점수(higher-low)**: 가격/ cRSI higher-low 기반 bottom_watch 강도 점수화. 종목 샘플 부족 + 프로토타입에서 참/가짜 역전 → 샘플 확보 후 분포 보고 설계.
