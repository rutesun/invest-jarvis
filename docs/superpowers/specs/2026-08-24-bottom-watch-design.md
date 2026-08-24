# bottom_watch 신호 설계

> 작성일: 2026-08-24
> 개정: 2026-08-24 (독립 리뷰 2건 반영 — 사실 오류/과적합/성공기준/구현 누락)
> 상태: **⛔ 검증 실패 → 보류.** §6 표본 검증에서 트리거가 시드 2종목 외 거의 발화 안 함(과적합 확인). 아래 "검증 결과" 참조. 후속: 바닥 사례 귀납 수집으로 전환.
> 관련 보류 항목: [ROADMAP.md] Task 13 저항 인식 패널티, Task 14 구조 점수(higher-low)

## 검증 결과 (2026-08-24, 구현 보류 결정)

편향 없는 표본으로 §6 검증을 실제 수행한 결과, **현재 트리거는 시드 2종목(엘앤에프·실리콘투)에 과적합**돼 일반화되지 않음이 확인됐다. 구현하지 않는다.

| 표본 | 트리거 수 |
|------|-----------|
| 시드 2종목 (하네스 재현 확인: 엘앤에프 7/10·7/31, 실리콘투 6/29 r20+12%) | 3건 |
| 대형주 30종목 × 3년 | 1건 (그마저 -8.5%, 손절) |
| 변동성주 6종목(HOOD/PGY/IONQ/ORCL/OKLO/JOBY) × 1년, 이중 divergence | 0건 |
| 위 6종목, 단일 divergence(≥15)로 완화 | 1건 |

**근본 원인**: 하락추세+최근 과매도 훅 "후보일"은 종목당 15~50일로 충분한데, 그 후보일에 **divergence가 거의 안 뜬다**(6종목 중 5종목의 후보일 최대 divergence = 0). 다이버전스 피벗(argrelextrema order=5)과 과매도 훅의 시점이 좀처럼 겹치지 않는다. 검증 표본(성능 측정용 트리거 수) 자체가 확보 불가 → §6 통과 기준 판정 불능.

**교훈**: 2종목·3시점으로 파라미터를 고정한 것이 과적합이었다(리뷰어 예측 적중). 신호를 먼저 정의하고 검증하는 순서가 아니라, **편향 없는 바닥 사례를 다수 수집해 공통 패턴을 귀납 추출한 뒤 정의**하는 순서로 전환한다. 하네스 코드: `tmp/sample_validation*.py` (참고용).

## 배경

현재 기술 스코어링은 추세 확인형(Minervini Stage 2, Supertrend)이라 하락추세가 무너졌다 되살아나는 국면에서 **바닥을 구조적으로 못 잡는다**. 엘앤에프·실리콘투 백테스트에서 divergence(다이버전스)와 cRSI 과매도 훅이 바닥을 정확히 짚었으나, aggregator가 divergence를 supertrend(-25)·minervini(-20)의 음수와 동등 합산해 최종 판정을 avoid로 눌렀다.

이 재료(바닥 신호)를 판정 action은 건드리지 않고 **별도 관찰 플래그**로 표면화하는 것이 목표다. 단, 아래 §6의 표본 검증으로 "무작위 진입보다 나은 필터인가"를 먼저 통과해야 구현한다.

### 백테스트 근거 (as-of 재현, 예비 관찰)

| 종목 | 날짜 | 가격 | 당시 action | 성격 |
|------|------|------|-------------|------|
| 엘앤에프 | 7/31 | 73,300 | avoid | 참 양성 (바닥, 이후 121,600) |
| 엘앤에프 | 7/10 | 100,500 | reduce | **가짜 양성** (이후 65,600까지 -35%) |
| 실리콘투 | 6/29 | 32,650 | reduce | 참 양성 (바닥 6/26=30,400) |

**이 3시점은 예비 관찰일 뿐 성능 근거가 아니다.** 종목 2개 모두 결국 반등에 성공한 표본이라 survivorship bias가 있고, 가짜 양성률을 알 수 없다. §6에서 편향 없는 표본으로 재검증한다.

## 설계

### 노출 방식 — 별도 플래그 병기

`action`/`adjusted_score`/`new_entry_allowed`는 **불변**. 기존 스윙 로직·테스트 무손상. `TechnicalVerdict`에 관찰 정보만 추가한다.

```python
class TechnicalVerdict(BaseModel):
    ...
    bottom_watch: bool = False
    bottom_watch_reason: str | None = None
    # invalidation_level(기존 필드)에 bottom_watch 손절 기준가를 채워 R/R 계산 가능하게 한다
```

의미: "지금은 추세상 회피(avoid/reduce)지만, 강한 역추세 바닥 클러스터가 포착됨. 정규 진입의 1/N 규모 탐색을 고려하되 손절선(§3.3) 이탈 시 청산." **buy 승격이 아니다** — 예비 관찰상 조기 신호의 상당수는 실패(엘앤에프 7/10)하며 손절로 방어하는 성격.

### 트리거 조건 — 논리 조건 + 윈도우 결합

이전 초안은 `divergence_score >= 35`로 썼으나, 리뷰에서 이 숫자의 실제 의미가 드러났다. `analyze_divergence`(`src/tools/technical/components/divergence.py`) 배점은:
- bullish RSI divergence = +15, bullish MACD = +10, bullish cRSI = +10
- **RSI와 cRSI가 동시 성립하면 누적 점수 전체에 ×1.5** (line 97-98)

따라서 `score >= 35`는 연속 강도 임계값이 아니라 **"RSI 강세 다이버전스 AND cRSI 강세 다이버전스 동시 성립"과 동치**다(그때만 ×1.5가 걸려 최소 37). 순수 삼중은 52. RSI+MACD만이면 25로 미달. 매직넘버 대신 **논리 조건**으로 명시한다:

```
bottom_watch = (
    context.is_downtrend
    AND divergence: (RSI 강세 divergence 성립 AND cRSI 강세 divergence 성립)   # 오실레이터 확증
    AND context.recent_oversold_hook            # 최근 N거래일 내 (cRSI<임계 & cRSI Hook Up)
    AND context.capitulation_volume             # (§5 후보 축) 검증 후 채택 여부 결정
)
```

- divergence 조건은 컴포넌트 signals/metadata에서 두 축(RSI·cRSI) 성립을 직접 확인한다. 배점(15/10/×1.5)이 바뀌어도 트리거가 깨지지 않게 **숫자가 아니라 신호 성립으로 판정**.
- 윈도우 결합 근거: 과매도 훅과 다이버전스가 같은 날 동시에 안 뜨고 시점이 어긋남(실리콘투: 훅 6/10 ↔ 다이버전스 6/29, 약 13거래일). 초안은 15거래일을 택했으나 **이 값은 §6 민감도 스윕으로 확정**한다(2종목 역산은 과적합).

**튜닝 파라미터 (상수 분리, §6에서 민감도 분석):**
- `BOTTOM_WATCH_HOOK_LOOKBACK` (거래일, 초기값 15 — 스윕으로 확정)
- `BOTTOM_WATCH_OVERSOLD_CRSI` (초기값 30)
- 거래량 확인 축 임계 (채택 시)

### 3.3 손절선(invalidation) 정량화

플래그와 함께 손절 기준가를 반드시 산출한다. 정의: **트리거 시점 룩백 윈도우 내 최저 종가(직전 스윙 저점)**. 이를 기존 `TechnicalVerdict.invalidation_level`에 채우고, formatter는 현재가 대비 하락률(%)을 병기한다. 이 값으로 R(리스크)이 정해져야 §6에서 손익비 기반 기대값을 계산할 수 있다.

### 아키텍처 — 윈도우 계산은 context, 판정은 aggregator

aggregator는 하루치 `components`+`context`만 받는 무상태 구조라 룩백을 직접 못 본다. `build_market_context(df)`는 df에 접근하므로 **여기서 윈도우를 계산해 `MarketContext`에 불리언을 주입**하고, aggregator는 그 필드만 읽는다. → aggregator 무상태 유지.

- `MarketContext`에 `recent_oversold_hook: bool`, (채택 시) `capitulation_volume: bool` 추가
  - cRSI Hook Up 판정은 `analyze_crsi`(`crsi.py:66`)의 `prev_crsi < low AND crsi > low` 로직을 **공통 헬퍼로 추출**해 최신 바뿐 아니라 과거 바에도 적용
  - **엣지 처리**: cRSI 밴드는 `min_periods=10` 롤링(`indicators.py:309`)이라 초기 ~30바는 NaN/불안정. 윈도우 내 유효 바가 부족하면 `recent_oversold_hook=False`로 폴백. NaN 밴드 바는 hook 판정에서 건너뛴다(조용한 False 방지 위해 명시적으로 skip).
- 플래그 계산은 **`_compute_bottom_watch(components, context)` 헬퍼로 분리**. divergence 축 성립은 `components["divergence"]`의 signals/metadata에서 읽는다(현재 aggregator는 `_collect_metadata`로 metadata만 수집하므로, 이 헬퍼가 divergence 신호를 직접 확인하는 경로를 담당).
- 세팅 위치: `ScoreAggregator.aggregate()`에서 verdict 생성(`aggregator.py:102`) 시 헬퍼 호출해 주입. 기존 조정 규칙(cap/override) 흐름 불변.

### downtrend_reversal_cap과의 관계 (정합성)

기존 `downtrend_reversal_cap`(`aggregator.py:63-75`)은 `is_downtrend AND bullish reversal 신호`일 때 adjusted≤35로 누른다. divergence bullish는 metadata에 `signal_type="reversal", bias="bullish"`를 심으므로(`divergence.py:109-117`), **bottom_watch 발동 케이스는 거의 항상 cap도 발동**한다. 관계를 이렇게 확정한다:

> **bottom_watch ⊆ downtrend_reversal_cap 발동 집합.** bottom_watch는 cap이 걸린 케이스 중 "RSI+cRSI 다이버전스 + 최근 과매도 훅"까지 겹친 상위 조건이다. cap은 점수를 누르고(방어), bottom_watch는 관찰 플래그를 켠다(표면화) — 방향이 상충하지 않는다.

어긋나는 케이스(cap 없이 bottom_watch만 켜짐)가 발견되면 골든 테스트로 박제하고 조건을 재검토한다.

### 클리어링 — 무상태 일별 재계산

플래그는 매일 재계산되는 무상태 값. 추세가 확인되면 `is_downtrend`가 False가 되어 자연히 꺼진다(엘앤에프 8/14 이후). 별도 만료 상태 없음.

### 출력

- **formatter**: `bottom_watch=True`면 판정 아래 한 줄 병기
  예: `⚠ 역추세 바닥 관찰: RSI+cRSI 다이버전스 + 최근 과매도 훅 | 손절 68,000(-7.2%) | 분할 탐색`
- **ScoreHistoryPoint**: `bottom_watch: bool` 필드 추가 + **생성부(`scorer.py:160-176`)에 `daily.technical_verdict.bottom_watch`를 명시 전파**(모델 필드만 추가하면 항상 False가 되므로 전파 코드 필수).

## §6 성공 기준 및 표본 검증 (구현 선결 조건)

골든 테스트(회귀)와 성능 평가(유효성)를 분리한다.

### 6.1 편향 없는 표본
- KR·US 각각에서 **하락 국면을 겪은 종목 20~30개**를 결과(반등/실패/횡보)와 **무관하게** 추출(survivorship bias 제거). 상장폐지·장기 횡보 종목도 포함.
- 각 종목의 3년 데이터에 트리거를 소급 적용해 모든 발동 시점을 수집(반등 성공 종목은 다이버전스가 연쇄로 여러 번 뜸 — 실패 케이스가 표본에 들어오게 해야 함).

### 6.2 성능 지표
- 신호 발동 후 N거래일(10/20/40) 시점 수익률 분포: **중앙값, 하위 25%, 승률(>0 비율)**
- 손절선(§3.3) 기준 평균 R, 손익비, 기대값
- 무작위 진입(같은 종목·같은 기간) 대비 우월성

### 6.3 통과 기준 (사전 고정)
- 신호 후 20일 수익률 **중앙값 > 0** AND **하위 25%가 손절선 이내** AND 무작위 진입 대비 개선.
- 파라미터 민감도 스윕(윈도우 10~25, cRSI 임계 28~32)에서 지표가 **평평(robust)**해야 함. 특정 값에서만 뾰족하면 과적합으로 판정하고 재설계.
- 거래량 확인 축(§5) 채택 시 가짜 양성률이 유의미하게 감소하는지 비교.

### 6.4 골든 테스트 (회귀 — 성능과 분리)
- 엘앤에프 7/31 → True, 실리콘투 6/29 → True, 엘앤에프 8/14 → False.
- 가짜 양성 엘앤에프 7/10은 **"현재 트리거의 알려진 한계"로 라벨링**하되, "통과로 박제"하지 않는다 — 트리거 개선으로 이 오탐이 걸러지면 테스트가 갱신돼야 한다(개선을 막지 않도록).
- action/adjusted_score가 기존과 동일하게 유지되는 회귀 테스트 포함.

## §5 확인 축 후보 (검토 대상)

현재 트리거의 세 조건(RSI div, cRSI div, cRSI 훅)은 모두 오실레이터 계열이라 상관이 높다 — 독립 확증이 약해 가짜 양성이 잘 안 줄어든다. **오실레이터 밖 확인 축**을 §6에서 비교 평가한다:
- **1순위: 항복성 거래량** — 신저점/훅 당일 거래량이 20일 평균 대비 급증. `context.volume_ratio_20d`가 이미 있어 비용 낮음.
- 후보: 반전 캔들 패턴, 지지 confluence(`nearest_support`/risk 스윙 로직 재사용).

채택 여부는 §6 결과(가짜 양성 감소 효과)로 결정한다. 효과 없으면 트리거에 넣지 않고 사유를 기록.

## 스코프에서 제외 (ROADMAP으로 이관)

- **Task 13 저항 인식 패널티**: 슈퍼트렌드 하락전환 직전 주요 고점(실리콘투 4/24=50,500)이 risk 컴포넌트의 최근 스윙 고점 5개(`tail(5)`)에 안 들어가 스코어링에서 안 보임. 미돌파 저항 밑에선 감점, 돌파 시 가산.
- **Task 14 구조 점수(higher-low)**: 프로토타입에서 참/가짜 바닥 역전(가격 higher-low는 바닥 당일 존재 불가). 샘플 확보 후 "확인 tier" 형태로 설계.
