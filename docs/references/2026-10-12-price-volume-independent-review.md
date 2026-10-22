# 가격·거래량 규칙 외부 독립 검토 — 인계용 연구 메모

- 보고서 기준일: 2026-10-12 · 수령/인계: 2026-10-13
- 출처: 사용자가 대화에 붙여넣은 「가격·거래량 기반 매매 규칙 독립 검토 보고서」
- 성격: 원문 전체 복사본이 아닌 핵심 주장·수치·출처 요약. 승인된 운영 규칙이 아니다.
- 검증 상태: 내부 코드의 기존 동작은 대조했다. 외부 URL·논문 내용·해당 일자의 가격은 이번 인계에서 독립 재검증하지 않았다. 원문의 검색 citation marker는 옮기지 않았다.

## 외부 결론
| 항목 | 외부 판단 | 권고 |
|---|---|---|
| 저거래량 음봉 Tennis Ball +15 | 반등 전 가점·장중 거래량 비교가 부적절 | B: 눌림 Observation 0점, 실제 반등 뒤 bullish evidence |
| 고거래량 음봉 Egg -15 | 투매 뒤 반전도 가능해 단순화가 큼 | 위험 Observation, 구조 실패 뒤 bearish 점수 |
| extension <=+5%만 검사 | -15%, -30%도 통과 | source별 adverse path·구조 무효화·양방향 한도 |
| 지지 touch·hold | 방향 전환 미확인 | WATCH, 별도 PULLBACK_REVERSAL_ENTRY |
| 실패 breakout 부활 | 과거 thesis·성과와 새 기회가 섞임 | old opportunity 종료, 새 Signal의 새 기회 |

## Tennis Ball/Egg의 의미와 근거
보고서는 Minervini의 *Think & Trade Like a Champion*(2017)에서 Tennis Ball을 눌림 뒤 빠른 회복으로 해석했다. 정확한 `음봉 거래량<최근 음봉 평균 50% →+15` 또는 `>150% →-15` 규칙의 동료심사 검증은 찾지 못했다고 밝혔다.

거래량의 추가 정보를 다룬 연구가 단일 저거래량 음봉의 bullish 예측력을 증명하지는 않는다. 고거래량 하락 뒤 기대수익 증가 연구도 이 시스템의 Egg 조건을 직접 검증한 것은 아니다. 정확한 threshold·weight는 heuristic(경험칙)과 실험 가설로 취급한다.

| 접근 | 보고서 평가 |
|---|---|
| A: FINAL에서 기존 +15 | 장중 측정 문제만 해소. 반등 미확인 문제는 남음 |
| B: 후보 0점, 실제 반등 뒤 +15 | 최종 추천. 확인 지연으로 놓치는 상승도 평가 |
| C: 장중 하루 거래량 환산 | 시간대별 volume curve 필요. 단순 시간 비례는 부적절. 보조 정보 권고 |

외부 lifecycle: `PROVISIONAL 저거래량 후보 0점 → FINAL 눌림 후보 0점 → FINAL 반등 Signal·bullish evidence`. Egg는 위험 후보→구조 실패 확인 뒤 bearish evidence. +15/-15는 기존과 비교하는 migration baseline이며 최적값은 아니다.

## EntryOpportunity 정의와 truth table 제안
| 상태 | 외부 정의 |
|---|---|
| ALLOW | source 유효·신선·가격/시장상 실행 가능 |
| WATCH | 추격·미확인 조정·지지 테스트·불완전 반등 등 가역적 대기 |
| BLOCK | source 유효하나 외부 시장 gate 닫힘 |
| INVALIDATED | 해당 source thesis 실패로 terminal 종료 |
| EXPIRED | 실패 없이 시간이 초과한 terminal 종료 |

핵심 행:
- bull·건강한 구조·정상 follow-through·허용 이격: ALLOW.
- +5% 초과: WATCH.
- 미확인 하락·지지 접근·종가 방어만 확인·불완전 반등: WATCH.
- adverse 한도 초과 또는 주요 지지 결정적 붕괴: INVALIDATED.
- `SMA150_EXIT` 등 후속 무효화: INVALIDATED.
- non-bull이지만 source 유효: BLOCK. 현재 시스템 sideways=WATCH와 다른 제안이다.
- 실패 없이 age 초과: EXPIRED. 최초 terminal 원인을 이후에 바꾸지 않음.
- 과거 실패 후 새 reversal: 새 source로 평가.

정상 소폭 하락 ALLOW와 미확인 소폭 하락 WATCH의 경계, 동시 조건 우선순위는 완전히 수치화하지 않았다.

## Adverse 한도 제안
```text
hard_adverse_limit_pct = clip(
    k_hard * ATR_at_signal / execution_reference_price,
    min_pct,
    max_pct
)
```
초기 가설은 `2 ATR`, `4% floor / 8% cap`. Signal 당시 ATR로 고정해 하락 중 허용폭이 커지는 것을 방지한다. 구조 붕괴와 adverse 한도를 OR로 결합한다. Supertrend down은 단독 hard invalidator보다 보조 evidence를 추천한다.

보고서는 adverse **경로** 위반을 terminal 처리하라고 하면서 최소 예시에는 현재 extension 검사만 적었다. 채택 시 과거 breach→회복을 포함해 prefix에서 최초 실패를 재계산해야 한다. 종가/저가 기준, FINAL/PROVISIONAL breach, expiry 우선순위는 미정이다. 보유·장부·DB를 필요로 하는 규칙은 아니다.

## 눌림 반등 확인 제안
```text
이전 완료 봉에서 PULLBACK_WATCH 존재
AND 지지 유지
AND Close_t > support
AND Close_t > max(High_t-1 ... High_t-N)
```
N=2를 초기 가설로 추천하고 1/2/3 비교. 거래량 확대·MACD·cRSI는 우선 Evidence로 기록하고 필수 조건으로 묶지 않는다. FINAL 종가 확인과 T+1 시가 체결을 연구 기준으로 제안했다.

old breakout #101 실패→#101 INVALIDATED·성과 보존→구조가 남으면 별도 WATCH→새 reversal #142→새 기준가 기회 흐름이다. `SUPERSEDED`는 필수가 아니며 lineage는 선택적 장기 제안이다.

## Parameter 초기 가설 — 모두 미검증
| Parameter | 초기값 | 실험 범위 |
|---|---:|---|
| PROVISIONAL Tennis/Egg weight | 0 | 0 |
| Tennis candidate/confirmed | 0 / +15 | 0,+5 / +5,+10,+15 |
| Egg candidate/confirmed | 0 / -15 | 0,-5 / -5,-10,-15 |
| low volume ratio | 0.50 | 0.40~0.90 |
| support proximity | 0.5 ATR | 0.25~1.0 ATR |
| watch expiry | 10봉 | 5~15 |
| reversal lookback | 2봉 | 1~3 |
| breakout opportunity age | 5봉 | 2~10 |
| pullback opportunity age | 3봉 | 1~5 |
| positive extension | +5% | +3~+8% |
| reconfirm adverse threshold | 1 ATR | 0.5~1.5 ATR |
| hard adverse threshold | 2 ATR | 1.5~3 ATR |
| hard adverse floor/cap | 4%/8% | 3~5% / 6~10% |
| support break buffer | 0.25 ATR | 0~0.75 ATR |
| mandatory rebound volume | false | false/true |
| optional rebound volume | 1.2배 | 1.0~1.5 |

## Backtest 제안 — 미실행
FINAL t까지 판정, t+1 실제 거래 가능 시가 체결. 다음날 시가를 Signal 생성에 사용하지 않는다. 후속 Opportunity도 해당 시점까지 평가한다. 시가 gap guard에 당일 고가·저가·종가를 사용하지 않는다.

거래량 분모는 t-1까지. 장중 추정 연구에는 시각이 있는 minute 데이터 필요. point-in-time universe·상장폐지·비용·slippage·시계열 walk-forward·미사용 test 기간을 고려한다.

단계 비교: V0 현행 → V1 FINAL-only 기존 점수 → V2 후보/확인 분리 → V3 양방향 한도 → V4 bounded ATR+구조 → V5 반등 N → V6 volume gate → V7 cRSI/MACD 추가 정보. C intraday는 별도 연구.

평가: expectancy, 승률·평균 손익, MAE/MFE, drawdown, false ALLOW, missed winner, time-to-MFE, age별 survival, regime별 성과. false ALLOW는 ALLOW 후 H=5/10/20봉 내 +1R보다 -1R/무효화에 먼저 도달한 비율 등으로 사전 정의한다. R·가상 체결은 Backtest 책임이다.

## 당시 사례 — 현재 가격 아님
이전 세션의 2026-10-12 장중 결과:
| 종목 | 당시 가격 | 5일 adjusted 점수 | 당시 Swing |
|---|---:|---|---|
| ALAB | $328.37 | 105→70→60→50→55 | ALLOW |
| COHR | $297.45 | 45→55→15→45→35 | INVALIDATED |
| INTC | $102.16 | 70→60→65→-25→-35 | ALLOW |

ALAB: 10/6 breakout $389.80, T+1 $376, 당시 -12.7%, SMA50 $317.80 위·상승 Supertrend·새 reversal 없음. INTC: 9/21 $121.78, T+1 $120.15, 당시 -15%, SMA50 $103.32 아래·Supertrend 하락·watch ACTIVE. COHR: 10/9 FINAL SMA150_EXIT로 INVALIDATED.

보고서는 외부 ALAB 10/9 close $342.21·10/12 프리마켓 $335.50, INTC 10/9 $104.70·프리마켓 $102.99도 확인했다고 주장했다. 서로 다른 시점이며 이번 인계에서 재검증하지 않았다.

최근 5일 Technical Score는 각 날짜까지 재계산한 adjusted_score이며 평균이 아니다. 전역 0~100 clamp가 없어 음수·115점도 가능하다. 별도 5축 Scorecard는 각 축 0~100이다. Tennis Ball +15는 legacy Technical Score volume component다.

## 주요 원 출처 — 접근·주장 재확인 필요
| 자료 | 저자·연도 | URL |
|---|---|---|
| Think & Trade Like a Champion | Minervini, 2017 | https://openlibrary.org/books/OL30209235M/Think_Trade_Like_a_Champion |
| Market Statistics and Technical Analysis: The Role of Volume | Blume/Easley/O'Hara, 1994 | https://doi.org/10.1111/j.1540-6261.1994.tb04424.x |
| Price Momentum and Trading Volume | Lee/Swaminathan, 2000 | https://doi.org/10.1111/0022-1082.00280 |
| The High-Volume Return Premium | Gervais/Kaniel/Mingelgrin, 2001 | https://doi.org/10.1111/0022-1082.00349 |
| Trading Volume and Serial Correlation in Stock Returns | Campbell/Grossman/Wang, 1993 | https://www.nber.org/papers/w4193 |
| Intra-Daily Volume Modeling and Prediction | Brownlees/Cipollini/Gallo, 2011 | https://doi.org/10.1093/jjfinec/nbq024 |
| Improving VWAP Strategies | Białkowski/Darolles/Le Fol, 2008 | https://doi.org/10.1016/j.jbankfin.2007.09.023 |
| Simple Technical Trading Rules | Brock/Lakonishok/LeBaron, 1992 | https://doi.org/10.1111/j.1540-6261.1992.tb04681.x |
| Foundations of Technical Analysis | Lo/Mamaysky/Wang, 2000 | https://www.nber.org/papers/w7613 |
| Support for Resistance | Osler, 2000 | https://www.newyorkfed.org/research/epr/00v06n2/0007osle.html |
| Data-Snooping, Technical Trading Rule Performance, and the Bootstrap | Sullivan/Timmermann/White, 1999 | https://doi.org/10.1111/0022-1082.00163 |
| A Reality Check for Data Snooping | White, 2000 | https://doi.org/10.1111/1468-0262.00152 |
| The Probability of Backtest Overfitting | Bailey/Borwein/López de Prado/Zhu, 2015 | https://ssrn.com/abstract=2326253 |
| The Deflated Sharpe Ratio | Bailey/López de Prado, 2014 | https://doi.org/10.3905/jpm.2014.40.5.094 |
| Survivorship Bias in Performance Studies | Brown/Goetzmann/Ibbotson/Ross, 1992 | https://doi.org/10.1093/rfs/5.4.553 |
| The Delisting Bias in CRSP Data | Shumway, 1997 | https://doi.org/10.1111/j.1540-6261.1997.tb03818.x |
| 보고서가 TA-Lib 문서로 제시한 링크 | 내용 미확인 | https://ta-lib.org/functions/supertrend.html / https://ta-lib.org/functions/crsi.html |
