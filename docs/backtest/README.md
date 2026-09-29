# 백테스트 실험 (preset v0)

대가 전략(Minervini / O'Neil / Weinstein)을 있는 그대로 백테스트해 비교하고, 어떤 성격의 주식에 어떤 preset이 먹히는지 데이터로 찾는 실험 묶음.

설계 배경: [../trading-system-implementation-design.md](../trading-system-implementation-design.md)
결과·해석: [results-log.md](results-log.md)

## 실행 방법

```bash
uv run python src/backtest/preset_v0.py           # 8개 티커 기본 비교
uv run python src/backtest/universe_matrix.py     # 62종목 베타·섹터 행렬
uv run python src/backtest/universe_extra.py      # 섹터당 신규 1종목(티커 OOS)
uv run python src/backtest/universe_holdout.py    # 기간 홀드아웃(IS/OOS)
uv run python src/backtest/universe_walkforward.py # 6개월 walk-forward
uv run python src/backtest/universe_market_filter.py # 시장 국면 필터
```

가격 데이터는 yfinance 수정주가, `tmp/bt_cache/`에 CSV 캐시된다.

## 코드 구조

- `preset_v0.py` — 재료(지표) 계산 + 3 preset 진입/청산/사이징 + `simulate()`. 다른 스크립트가 재사용.
- `universe_matrix.py` — 섹터 태그 유니버스, 실측 베타, (preset × 성격) 행렬.
- 나머지 스크립트는 위 둘을 import 해 검증 방식만 바꾼다.

## preset 정의 (v2, 웹 교차검증 심화 반영)

| | 진입 | 초기 손절 | 청산 |
|---|---|---|---|
| MINERVINI | Stage2 + 50일 신고가 돌파 + 거래량 1.4x + 52주고 75%↑ + **RS>0(vs SPY 6M)** + 과열 아님 | **진입 -8%** | **+8%(=+1R)에서 절반 익절**(원래 스탑 유지 → room), 잔여 종가<SMA50 이탈 |
| ONEIL | 상승추세 + 50일 신고가 돌파 + 거래량 1.5x | 진입 -8% | +25% 절반 익절, **급등리더(1~3주 +20%)는 8주(40거래일)간 청산 무시** 후 종가<SMA50 |
| WEINSTEIN | close>SMA150(상승) + 50일 신고가 돌파 + 거래량 2배 | SMA150/진입-3·ATR (넓게) | 종가<SMA150 이탈 (넓은 추적, 분할 없음) |
| BUY&HOLD | 첫날 매수 | — | 끝까지 보유 |

v2 변경(원문 근거): 미네르비니 분할은 +25%가 아니라 "**+8%에 절반 팔고 나머지는 원래 스탑까지 room**"(원문), 손절 -8% 고정, RS>70 근사 필터. 오닐 8주 보유 법칙(급등주도주 40거래일 청산 유예). ([finermarketpoints SEPA/VCP](https://www.finermarketpoints.com/post/what-is-mark-minervini-s-trading-strategy-the-complete-sepa-vcp-guide), [SEPA framework](https://www.finermarketpoints.com/post/mark-minervini-s-sepa-methodology-complete-framework-explained))

R = (청산가-진입가) ÷ 초기위험(진입가-초기손절). "작게 잃고 크게 먹기"를 재는 단위.

### 실제 방법론 대비 충실도 (웹 교차검증)

- **오닐**: 손절 -7~8%·순방향 이동, 20~25% 분할익절, 급등리더 8주 보유 → 우리 preset과 잘 일치. ([ChartMill](https://www.chartmill.com/documentation/trading-and-investing/methodologies/527-William-ONeils-7-8-Sell-Rule-Explained), [CAN SLIM](https://en.wikipedia.org/wiki/CAN_SLIM))
- **와인스타인**: 30주선(=150일) 돌파를 **거래량 2배**로 확인, 30주선 이탈 시 청산 → v1에서 거래량 필터 추가로 정합. ([TraderLion](https://traderlion.com/trading-strategies/stage-analysis/))
- **미네르비니**: Trend Template(52주고 75%↑ 포함) + VCP 베이스 pivot, 손절 7~8%/수축 저점, 20~25% 분할 + 21/50 EMA 트레일 + 50/150 이탈 전량 → v1에서 52주고 필터·SMA50 트레일·분할익절 반영. ([finermarketpoints](https://www.finermarketpoints.com/post/what-is-mark-minervini-s-trading-strategy-the-complete-sepa-vcp-guide))
- **남은 한계**: 세 진입 모두 실제 베이스 패턴(VCP/컵핸들/저항돌파)이 아니라 "50일 신고가 돌파" 범용 프록시를 씀 → 진입 차별화가 실제보다 약함. 차별화는 주로 청산에서 나옴.

## 공통 규칙·한계 (모든 결과에 적용)

- look-ahead 차단: 신호는 t 종가로 계산, 체결은 t+1 시가. 스탑·목표 동시 도달 시 스탑 우선(보수적).
- **거래비용 미반영** (사용자 요청). 자주 거래하는 preset에 유리하게 편향.
- **생존편향 잔존**: 현재 상장 종목만. buy&hold가 체계적으로 부풀려짐.
- **단일 5년 구간**(2021-09~2026-09), 상폐/시점정합 유니버스 없음.
- 셀별 표본이 작을 수 있음(특히 섹터×preset). 매매수 적은 셀은 노이즈.
- preset은 v0 단순화판 — 대가 원칙의 근사이지 정본이 아님.
