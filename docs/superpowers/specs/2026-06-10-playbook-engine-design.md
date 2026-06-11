# Playbook Engine 설계 스펙

- **작성일**: 2026-06-10
- **상태**: Draft v4 (1·2차 리뷰 + 한국 업종 데이터 확보 반영)
- **대상**: 5대 추세추종·모멘텀 대가(리버모어·터틀·오닐·와인스타인·미너비니)의 매매 규칙을 `analyze`(deep_dive) 파이프라인에 적용
- **출처 자료**: `docs/references/trading-playbook.md`, `docs/references/trading-legends-report.md`

---

## 0. 변경 이력 (리뷰 반영)

### 0.1 1차 리뷰 반영 (R1~R15)

| # | v1 문제 | 반영 |
|---|---|---|
| R1 | veto 대상 `actionable_signal`이 analyze 화면에 표시 안 됨 | veto를 **`decision_summary`**에 반영 (§12) |
| R2 | "한국은 분기 EPS 없음" 오해 | KIS는 `FID_DIV_CLS_CODE="1"` 분기 지원 (§7.2). ※2차에서 EPS 필드 과장 추가 교정(R20) |
| R3 | 셋업 E를 `pattern_engine` 재사용이라 기재 | VCP 신규. ※2차에서 `patterns._detect_vcp` 일부 존재로 교정(R21) |
| R4 | Stage2 출처 모호 | ※2차에서 Stage2 이중 정의 발견, 단일 출처로 통일(R16) |
| R5 | regime/RS 자체 fetch | `IndexProvider`로 fetch 분리, 두 모듈 순수화 |
| R6 | `annual_data` 과소평가 | 모델+요약+렌더 변경 명시 |
| R7 | `invalidation_zone` 단일가 오인 | zone `lower_bound` 사용 + engine 입력에 zone_set |
| R8 | `SMA21` 코드에 없음 | ※2차에서 `SMA_20` 재사용으로 확정(R22) |
| R9 | 매집일 정의 비원전 | 오닐식(전일 대비 거래량+종가 위치) 정정 (§7.1) |
| R10 | 매도 신호 강도/매핑 모순 | 단기이평=비중축소, 장기선=청산 (§11) |
| R11~R14 | 손절 가드·결측·엣지케이스 | §10·§6.3·§20 |
| R15 | 섹터/업종 동조 누락 | 업종 강도 도입. ※2차에서 **가점**으로 확정(R23) |

### 0.2 2차 리뷰 반영 (R16~R25) + 사용자 결정

| # | 2차 발견 | 반영 |
|---|---|---|
| R16 | **Stage2 정의가 2곳에 다름** (`indicators.Is_Stage2` 4조건 vs `minervini` 5조건) | `minervini.py`가 `df`의 `Is_Stage2` 컬럼을 읽어 metric 노출 → **단일 출처**. 중복 제거 (§6.1, §0.3) |
| R17 | veto 결합도(순수함수에 주입) + 네이밍 | `apply_playbook_veto` 별도 순수 함수 분리, `action_original`(LLM 아닌 규칙 출력) (§12, §14) |
| R18 | 한국 EPS는 "1줄" 아님 | R6 비용으로 재분류: div_cls+6메서드+growth-ratio+파싱+필드 (§7.2, §19) |
| R19 | §14 result 모델 6개 누락 | 전부 스케치 추가 + `PlaybookVerdict.sector_strength` (§14) |
| R20 | growth-ratio "EPS 직접" 과장 | ~~순이익 fallback~~ → **D3에서 개선**: profit-ratio의 EPS '값'을 분기/연간으로 받아 증가율을 직접 계산 (§7.2) |
| **D3** | **[사용자 지적] EPS 증가율 직접 계산** | growth-ratio(순이익증가율)에 의존하지 않고, KIS 수익성비율(`get_profit_ratio`)의 **EPS 필드(실재, fundamental.py:366)를 분기/연간 시계열로** 받아 `(당기−전년동기)/전년동기`로 C·A 산출. 분기·기간 부족 시에만 순이익 fallback (§7, §7.2) |
| **D4** | **[사용자 결정] Stage2 7조건 보강** | 미너비니 원전 조건 4(50>150>200 정배열)·5(종가>SMA50) 추가 → 4조건→7조건. RS(8번)는 C★ 별도 (§0.3) |
| **D5** | **[사용자 지적] 단일 출처 = minervini (SRP + 죽은코드 제거)** | `IndicatorCalculator`는 공통 원자 지표만. `indicators._calculate_stage2`·`Is_Stage2` 컬럼 **제거**(grep 확인: 소비처 없는 죽은 코드). Stage2 7조건 판정·점수·`is_stage2` metric을 모두 `minervini.py`로 일원화 (§0.3, §4.3) |
| R21 | **VCP가 `patterns._detect_vcp`에 일부 존재** | "전무" 아님 → 수축은 재사용, **피벗 돌파만 신규**, 이중 구현 회피 (§6.1 E) |
| R22 | `SMA_21` 신규 실익 없음 | `SMA_20` 재사용으로 확정 (§11) |
| R23 | 업종 위상 | ~~가점~~ → **D2에서 C★ 필수로 재승격**(한국 업종 데이터 확보로 비대칭 해소) |
| R24 | yfinance↔FMP 업종명 불일치 | "동일 체계" 삭제, **정규화 매핑 레이어** + 실패 시 None (§9.1) |
| R25 | FMP historical 무료 게이팅 | snapshot-only degrade 단계 + 엔드포인트별 플랜 리스크 (§9.1) |
| **R26** | **한국 업종 데이터 "없음"은 오류** | KIS 업종지수 API(`inquire-index-category-price`/`inquire-daily-indexchartprice`/`inquire-index-daily-price`) 실재 → **한국도 업종 강도 지원**. `sector_strength`는 FMP(미국)+KIS(한국) 2구현 → 추상 인터페이스 정당(YAGNI 해소) (§4.1, §9.1) |
| **D1** | **[사용자 결정] 한국 수정주가** | KIS `get_price_history`에 수정주가 적용(`FID_ORG_ADJ_PRC` 변경) + 기존 기술분석 회귀 검증 (§20, §19) |
| **D2** | **[사용자 결정] 업종 = C★ 필수** | 한·미 모두 업종 데이터 확보 → 종목 RS + 업종 RS 둘 다 충족해야 신규매수 통과. 업종 매핑 실패·결측 종목만 종목 RS로 graceful (§6.1, §6.3, §9.1) |

### 0.3 단일 출처 원칙 + Stage2 7조건 보강 (R16, D4, D5)
Stage2 판정의 **유일 출처는 `minervini.py`**다(SRP, D5): `IndicatorCalculator`는 SMA·RSI 등 공통 원자 지표만 담당하고, 미너비니 전략 고유 판정인 Stage2는 `minervini.py`가 맡는다. **`indicators._calculate_stage2`와 `Is_Stage2` 컬럼은 제거**한다 — grep 확인 결과 읽는 소비처가 없는 죽은 코드였다(`models.py:362` 화이트리스트만 보존).
`minervini.py`가 미너비니 추세 템플릿 **7조건**을 판정(D4):
1. 종가 > SMA150 > SMA200  2. SMA150 > SMA200  3. SMA150·SMA200 상승  4. **50>150>200 완전 정배열(신규)**  5. **종가 > SMA50(신규)**  6. 52주 저점 ×1.3 이상  7. 52주 고점 ×0.75 이상.
RS(원전 8번)는 게이트 C★에서 `relative_strength`로 별도 처리(중복 방지).
출력: `metrics["is_stage2"]`(1.0/0.0) + score/signals. 게이트 B는 이 metric만 참조.

---

## 1. 배경 및 목표

invest-jarvis는 이미 풍부한 기술적 분석·펀더멘털·뉴스·수급·구조 zone을 LLM으로 종합해 `analyze`에서 결정 요약(`decision_summary`)을 낸다. 그러나 5대가 플레이북의 두 축 — **(a) 매수 자격 판정**, **(b) 실전 매매 의사결정(사이징·손절·매도)** — 으로 종합하는 층이 비어 있다.

**목표**: 기존 지표를 최대한 재사용하면서, "결정론적 게이트(veto) → 포지션 사이징/매도 판정 → LLM 해석" 흐름을 새 `playbook` 패키지로 분리해 `analyze`에 얹는다.

**핵심 원칙**: **사실은 코드가, 해석은 LLM이.** 규칙이 명확한 체크리스트·수식은 결정론 코드로, LLM은 해석. 규칙 원전은 `docs/references/` 2종 기준.

---

## 2. 범위

### 포함
- 매수 자격 게이트 (시장환경·Stage2·종목 상대강도·셋업 ★ + 가점)
- 포지션 사이징 (위험 1~2% → 수량/R/손절/목표)
- 보유 종목 매도·추세종료 판정 (5단계)
- 보유 상태 YAML (수량·평단·자본)
- CAN SLIM 정량화 (C·A·I + 업종 L 가점)
- 시장환경·종목 RS·업종 강도(가점)·VCP 신규 모듈

### 제외
- KIS 계좌 잔고 자동 연동 (YAML 대체) / 매매 일지 / 피라미딩
- IBD 백분위 RS Rating + **업종 내 1~2등 순위**(유니버스 필요 → `screen` 추후)
- 백테스트, 포트폴리오 리스크 집계, 멀티레그

---

## 3. 핵심 설계 결정 (요약)

| 결정 | 확정 | 비고 |
|---|---|---|
| 진입점 | `analyze`(deep_dive) 강화 | |
| 범위 | 신규 진입 + 보유 매도 판정 | |
| 보유 관리 | YAML | |
| 아키텍처 | `playbook` 패키지 (결정론 + LLM 해석) | |
| 게이트 권한 | **veto** → `decision_summary` (R1, R17) | |
| **C★ veto** | **종목 RS + 업종 RS** (둘 다 필수) | D2 사용자 결정 |
| Stage2 출처 | `indicators.Is_Stage2` 단일 (R16) | |
| CAN SLIM | C·A·I 신규, N·S·L·M 참조 | |
| C(EPS) | 미국 yfinance EPS, 한국 **순이익증가율 fallback** | R20 |
| 업종 강도 | **C★ 필수**. 미국=FMP, 한국=KIS 업종지수. 2구현 인터페이스 | D2, R26 |
| 한국 가격 | **수정주가 적용** | D1 사용자 결정 |

---

## 4. 아키텍처

### 4.1 모듈 구조

```
src/providers/
  index_provider.py     # 시장지수(^GSPC/^KS11/^KQ11) OHLCV fetch  [신규]
  fmp_provider.py       # FMP 업종 perf fetch (미국)  [신규]
  kis.py (확장)         # 업종지수 API 추가: inquire-index-category-price / inquire-daily-indexchartprice / inquire-index-daily-price (한국, R26)

src/tools/playbook/
  __init__.py
  models.py             # 결과 스키마 (pydantic) — §14 완비
  market_regime.py      # 지수 추세 판정 (순수: index_df → result)
  relative_strength.py  # 종목 맨스필드 RS (순수: stock_df + index_df)
  sector_strength.py    # 업종 강도/추세 — 추상 인터페이스 + FMP(미국)·KIS(한국) 2구현 (R26). C★ 필수 입력
  vcp.py                # VCP 피벗 돌파 감지 (patterns._detect_vcp 수축 결과 + 돌파 신규, R21)
  canslim.py            # CAN SLIM (C·A·I 신규)
  accumulation.py       # 매집일/분산일 (오닐식)
  gate.py               # 매수 자격 체크리스트
  sizing.py             # 포지션 사이징
  exit_rules.py         # 추세 종료 5단계 매도
  holdings.py           # YAML 보유·계좌 로더
  engine.py             # 통합 → PlaybookVerdict
```

### 4.2 의존성 + 실행 순서 (R-Q3)

```
IndexProvider (fetch) ─┐  index_df
FmpProvider   (fetch) ─┤  industry perf (미국만; 한국 skip)
                       ↓
engine.evaluate(순서 보장):
  1) 기초 판정(병렬, 순수): market_regime(index_df), relative_strength(stock_df,index_df),
                            sector_strength(industry, fmp_data), vcp(df), accumulation(df)
  2) canslim(위 결과 + fundamental 참조)        # 1)의 출력을 입력으로
  3) if 미보유: gate(위 결과 전부 주입) → sizing(gate PASS + risk metrics + zone_set)
     if 보유:  exit_rules(df + RS + accumulation + holding)
  4) build_analyze_decision_bundle(...) → apply_playbook_veto(summary, verdict)
```

- 외부 fetch는 `IndexProvider`/`FmpProvider`만. playbook 내부는 전부 순수 함수(DataFrame/결과 주입). `sector_strength`도 순수(데이터 주입), fetch는 `FmpProvider` 책임.
- `gate`는 하위 모듈을 호출하지 않고 engine이 만든 결과 객체만 받음(단방향).

### 4.3 기존 파일 변경

| 파일 | 변경 |
|---|---|
| `src/providers/index_provider.py` | **신규** 지수 OHLCV |
| `src/providers/fmp_provider.py` | **신규** FMP 업종 perf. `FMP_API_KEY` 환경변수 |
| `src/providers/kis.py` | `_get_finance_data` `div_cls_code` 인자화 + 6개 메서드 + `get_growth_ratio` (R18); **`get_price_history` 수정주가** `FID_ORG_ADJ_PRC` (D1); **업종지수 API 3종 신규** + 종목→업종코드 매핑 (R26) |
| `src/tools/fundamental.py` | `annual_data` + `QuarterlyData.eps/eps_yoy` + 한국 growth-ratio 파싱 (R6, R18, R20) |
| `src/tools/technical/indicators.py` | `_calculate_stage2`·`Is_Stage2` 컬럼 **제거**(죽은 코드, SRP, D5); `models.py:362` 화이트리스트에서도 제거 |
| `src/tools/technical/components/minervini.py` | **Stage2 단일 출처**: 7조건(보강) 판정 → score·signals·`metrics["is_stage2"]` (R16, D4, D5) |
| `src/pipelines/analyze_decision.py` | `apply_playbook_veto` 신규 순수 함수 (R17); `build_analyze_decision_bundle`은 순수성 유지 |
| `src/llm/models.py` | `AnalyzeDecisionSummary`에 `action_original`, `veto_applied` (R17) |
| `src/cli/main.py` | "📋 플레이북 평가" 섹션 + 펀더멘털 연간 렌더 |
| `src/tools/playbook/holdings.py` | YAML 로딩, `is_korean_ticker` 재사용 |

> `SMA_20`은 이미 존재 → 매도 규칙은 SMA_20 재사용, 신규 지표 0개 (R22).

---

## 5. 데이터 흐름 (analyze 내부)

```
analyze(ticker)
  ├ 기존: technical(3y), fundamental, news, flow, patterns, zone_set ...
  ├ [NEW] index_df = IndexProvider.get(ticker)
  ├ [NEW] industry_perf = FmpProvider.get(ticker) if not is_korean_ticker else None
  ├ [NEW] holding = holdings.load("playbook.yaml").find(ticker)
  ├ [NEW] verdict = playbook.engine.evaluate(
  │         ticker, technical_result, fundamental, flow, zone_set,
  │         index_df, industry_perf, holding)   # §4.2 순서
  ├ [NEW] bundle = build_analyze_decision_bundle(...)        # 순수 유지
  │        summary = apply_playbook_veto(bundle.summary, verdict)  # veto 후처리 (R17)
  └ 출력 dict: 기존 + "playbook_verdict"
```

---

## 6. 매수 자격 게이트 (`gate.py`)

### 6.1 ★ 필수 항목 (하나라도 FAIL → 부적격, veto)

| # | 항목 | 판정 | 출처 |
|---|---|---|---|
| A | 시장 환경 | 지수 SMA50·SMA200 위 + SMA200 우상향 | `market_regime` (index_df) |
| B | Stage 2 | `components['minervini']['metrics']['is_stage2'] == 1.0` (= `indicators.Is_Stage2` 단일 출처, R16) | `minervini.py`→`Is_Stage2` |
| C | 상대강도 (종목 + 업종) | 종목 Mansfield RS > 0 + RP 4주 기울기 ≥ 0 **AND 종목 업종이 시장 대비 강세**(미국 FMP / 한국 KIS 업종지수). 업종 매핑 실패·결측 종목만 종목 RS로 판정(D2 graceful) | `relative_strength` + `sector_strength` |
| E | 셋업 | **VCP 피벗 돌파** + 돌파일 거래량 ≥ `Vol_SMA_50×1.5` | `vcp.py` + `volume.py` |

> **E (R21)**: VCP 수축 판정은 기존 `patterns._detect_vcp`(ATR 수축률) 결과를 **참조**. 그러나 거기엔 "마지막 수축 피벗의 상향 돌파" 로직이 없으므로 `vcp.py`는 **돌파 판정만 신규**(수축 재계산 금지, 이중 구현 회피).

### 6.2 가점 항목 (품질 등급용, veto 아님)

| 항목 | 판정 | 출처 |
|---|---|---|
| D 펀더멘털 (CAN SLIM C·A) | 분기 EPS증가율≥25%, 연 성장≥25%, ROE | `canslim` |
| I 기관(거래량 매집) | 매집일 우세 / Pocket Pivot | `accumulation`, `volume` |
| 수급 직접확인 (한국) | 외인·기관 순매수 | `flow` |

> 업종 강도(L)는 **C★ 필수로 이동**(D2). CAN SLIM의 L 항목(§7)은 `sector_strength` 결과를 **참조**만 한다(이중 점수 금지).

### 6.3 출력 + 결측(None) 처리

- `passed`, `checklist: list[GateCheck]`, `quality_grade`, `veto_reason`
- **★ 항목 전체가 None이면 보수적 부적격** + `veto_reason="데이터 제한: {항목}"`.
- **C의 부분 결측 (D2 graceful)**: C는 "종목 RS"와 "업종 RS"의 AND. **업종 데이터가 결측·매핑 실패면 그 종목만 종목 RS로 C를 판정**(업종 조건 생략, 막지 않음). 종목 RS까지 없을 때만 C = None → 부적격. 출력에 "업종 미확인" 라벨.
- 가점 None은 quality_grade 분모에서 제외.

---

## 7. CAN SLIM 매핑 (`canslim.py`)

| | 의미 | 구현 | 데이터 |
|---|---|---|---|
| **C** | 분기 EPS 급증 | 분기 **EPS YoY** ≥ +25% + 가속 | 미국 `quarterly_data[].eps_yoy` / 한국 **profit-ratio EPS 분기 시계열 → YoY 직접 계산**(D3). 분기·기간 부족 시에만 순이익 fallback |
| **A** | 연간 이익 성장 | 연 EPS/순이익 성장 ≥ +25% + 다년 추세 + ROE | `annual_data`, growth-ratio 연간 |
| **N** | 새로움 | 52주 신고가 −25% 이내(참조) + 신제품·경영진 LLM | `minervini` metrics, `news`, `disclosure` |
| **S** | 수급 | 돌파일 거래량(참조) + 유통주식 | `volume`, `float_shares`(미국) |
| **L** | 주도주(업종) | 종목 업종이 강세 (R23 가점) | `sector_strength` 참조 |
| **I** | 기관 매수 | 거래량 매집(오닐식) + 한국 flow | `accumulation`, `volume`, `flow` |
| **M** | 시장 방향 | 지수 상승추세 | `market_regime` 참조 |

> **C·A 입력 일원화 (R20)**: C/A는 신규 `eps_yoy`/연간 EPS를 우선 사용. EPS 데이터 결측 시 **순이익증가율 fallback**(품질 등급 강등, `detail`에 "순이익 기반" 표기). 한국 KIS growth-ratio가 EPS증가율을 제공하는지는 §7.2 실호출로 검증.

### 7.1 매집일/분산일 (`accumulation.py`) — 오닐식 (R9)
- **분산일**: 종가 전일 대비 −0.2% 이상 하락 AND 거래량 전일 대비 증가.
- **매집일**: 종가 전일 대비 상승 AND 거래량 전일 대비 증가 AND 종가 레인지 상단(`(close-low)/(high-low) ≥ 0.5`).
- 최근 25거래일 → `accumulation_ratio`. Pocket Pivot은 `components['volume']` 참조.

### 7.2 fundamental.py + kis.py 확장 (R6, R18, R20, D1, D3)
- **kis.py**:
  - `_get_finance_data(..., div_cls_code="0")` 인자화 → 호출 6개 메서드 시그니처 변경. 분기 `"1"`.
  - **profit-ratio를 분기/연간으로 받아 EPS '값' 시계열 확보**(D3): `get_profit_ratio`에 `div_cls_code` 전달. EPS 필드는 이미 응답에 존재(`fundamental.py:366`).
  - `get_growth_ratio` 신규는 **보조**(순이익증가율 — 교차검증·fallback).
  - `get_price_history` **수정주가 적용**(`FID_ORG_ADJ_PRC` 변경, D1).
- **fundamental.py**:
  - `QuarterlyData`에 `eps`, `eps_yoy` 추가. **profit-ratio 분기 EPS로 `_build_kis_quarterly_data`가 YoY 직접 계산**(당기 EPS vs 4분기 전 EPS). 현재는 QoQ만.
  - `FundamentalSnapshot.annual_data: list[AnnualData] | None`(연도별 EPS 포함).
- **변경 범위(R6)**: 모델 + 로직 + LLM 요약 입력(`FundamentalSummaryInput`) + CLI 렌더(`main.py:690`). "1줄" 아님.
- **구현 전 실호출 검증(D3)**: (a) profit-ratio가 분기(`div_cls="1"`)를 지원하는지, (b) **전년 동기 비교용 최소 5개 분기 EPS**를 주는지, (c) 수정주가 회귀. → (a)·(b) 불가 시에만 연간 EPS 또는 순이익(growth-ratio) fallback.

---

## 8. 종목 상대강도 RS (`relative_strength.py`) — RSI와 별개

> RS(상대강도, 종목 vs 시장) ≠ RSI(`indicators.py:32`). 본 모듈은 RSI 미사용. (리뷰 검증 통과)

- `RP[t] = 종목종가 / 지수종가`; `Mansfield RS = (RP / SMA(RP,252) − 1)×100`
- 판정: `Mansfield RS > 0` AND `RP 4주 기울기 ≥ 0` → C★ 통과 (종목 한정, 업종 무관)
- 출력: `RelativeStrengthResult { mansfield_rs, outperform_6m, rp_slope_4w, is_strong, index_symbol }`

---

## 9. 시장 환경 게이트 (`market_regime.py`) — 순수 함수
- 입력: `IndexProvider`의 `index_df`. 지수 매핑: 미국 `^GSPC`, 코스피 `^KS11`, 코스닥 `^KQ11`(§20 판별)
- 판정: `종가 > SMA50` AND `> SMA200` AND `SMA200 우상향` → 신규매수 허용
- 출력: `MarketRegimeResult { regime, allow_new_buy, index_symbol, detail }`

### 9.1 업종 강도 (`sector_strength.py`) — C★ 필수 입력 (R26, D2)

**추상 인터페이스 + 2구현**(데이터 소스가 미국·한국 2개 → 인터페이스 정당, YAGNI 해소): `SectorStrengthProvider` 인터페이스 + `FmpSectorStrength`(미국)·`KisSectorStrength`(한국). 판정 로직은 순수 함수(데이터 주입), fetch는 각 provider.

- 입력: 종목 업종 — 미국 `FundamentalSnapshot.industry`(yfinance), 한국 KIS 업종코드(종목→업종 매핑).
- **미국 (FMP)**:
  - `industry-performance-snapshot` → 업종 순위(백분위) = 오닐 IBD 업종 순위 근사
  - `historical-industry-performance` → 업종 추세 = 와인스타인 "업종도 2단계"
  - 업종명 매핑(R24): yfinance↔FMP 택소노미 불일치(구분자·복수형) → 정규화 + fuzzy. 실패 → None.
  - degrade(R25): historical 무료 게이팅 시 snapshot 순위만으로 판정.
- **한국 (KIS, R26)**:
  - `inquire-index-category-price` → 전체 업종 시세 → 업종 순위(오닐 IBD 근사)
  - `inquire-daily-indexchartprice` → 업종지수 OHLCV → 업종 추세(상승/Stage2) + 코스피 대비 강도(와인스타인)
  - 종목→업종코드 매핑은 KIS 종목정보(구현 시 확인). KRX 업종 granularity는 GICS보다 거침(~20여 개).
- **판정**: 업종이 시장 대비 강세(순위 상위) AND 추세 양수 → 업종 강함 → C★의 AND 조건 충족.
- **결측 (D2 graceful)**: 매핑 실패·API 키 없음·업종 데이터 없음 → `is_strong=None` → C는 종목 RS만으로(§6.3).
- 출력: `SectorStrengthResult { industry, rank_pct: float|None, trend: str, is_strong: bool|None, source: str }` (source="FMP"|"KIS")
- **리스크**: FMP 무료 티어(약 500MB/월, 250 req/day, US-only) + 엔드포인트 플랜 게이팅; KIS 업종 매핑 신뢰도·granularity. 일 단위 캐시(장 마감 후 확정).
- **업종 내 1~2등 순위는 미검증**(§18): "강한 업종에 속함"까지만. "그 업종 내 주도주"는 유니버스 필요 → CLI에 "업종 동조 확인(업종 내 순위 미검증)" 라벨.

---

## 10. 포지션 사이징 (`sizing.py`)

### 손절가 선택 (R7, R11)
후보: ① −7~8% 고정 ② `components['risk']['metrics']['stop_loss']`(2×ATR) ③ `zone_set.invalidation_zone.lower_bound`(None 가능 → 건너뜀)
- 가장 타이트한 후보. `최소 손절폭 3%` 미만 → 다음 후보. **상한 가드**: 모두 −8% 초과면 진입 부적격(`risk_too_wide`).

### 수량/R (R12)
```
per_share_risk = entry − stop
if per_share_risk <= 0: → invalid_stop, shares=None, 경고
shares = floor((capital × risk_pct) / per_share_risk)
```
목표 `+2R/+3R`. 자본 미입력 → 비율 모드.
출력: `PositionPlan { entry, stop, stop_basis, per_share_risk, shares: int|None, position_value, weight_pct, r_targets, capital_mode, error }`

---

## 11. 매도·추세 종료 (`exit_rules.py`) — 보유 종목 (종가 기준, R10)

| # | 신호 | 판정 | 강도 |
|---|---|---|---|
| 1 | 성격 변화 | 신고가 실패 또는 스윙 저점(swing low) 이탈 | 약 |
| 2 | 단기 이평 이탈 | 종가 < **SMA_20** 또는 SMA50 (R22) | 중 |
| 3 | 분산 거래량 | `accumulation` 분산일 누적 | 중 |
| 4 | RS 약화 | Mansfield RS 음전환 | 약 |
| 5 | 장기 이평 이탈 | 종가 < SMA150/200 + 기울기 꺾임 | 강(확정) |

판정: **강(5)→청산**, **중(2/3)→비중축소**, 약(1·4)→경고+보유. 중 2개↑→청산 검토.
- `current_r`: YAML에 `stop_price` 없으면 **None**(임의 −8% 가정 금지) + "평단 대비 ±X%"만. 트레일링: SMA50 기본.
- 출력: `ExitVerdict { action, signals, current_r: float|None, trailing_stop, detail }`

---

## 12. veto — `decision_summary` 후처리 (R1, R17)

```
bundle  = build_analyze_decision_bundle(...)          # 순수 유지 (책임 분리)
summary = apply_playbook_veto(bundle.summary, verdict)  # 신규 순수 함수
```

| 상태 | `apply_playbook_veto` 처리 |
|---|---|
| 미보유 + 게이트 FAIL | `action="관망"` + `action_sentence="신규진입 부적격: {veto_reason}"`, 사이징 생략 |
| 미보유 + PASS | 유지 + PositionPlan 첨부 |
| 보유 | `exit_verdict` 우선(청산/비중축소) |

- 원본 보존: `AnalyzeDecisionSummary.action_original`(덮기 전 **규칙** 출력 — LLM 아님, R17), `veto_applied: bool`.
- "📋 플레이북 평가" 섹션을 출력 최상단에.

---

## 13. YAML (`playbook.yaml`, `holdings.py`)

```yaml
account:
  krw: { capital: 50000000, risk_per_trade_pct: 1.0 }
  usd: { capital: 30000,    risk_per_trade_pct: 1.0 }
holdings:
  - { ticker: AAPL,        quantity: 10, avg_price: 180.5 }            # stop_price 선택
  - { ticker: "005930.KS", quantity: 50, avg_price: 70000, stop_price: 64000 }
```
- 통화 판별 `is_korean_ticker` 재사용. `account` 없음 → 비율 모드. `stop_price` 있으면 §11 R 정확.

---

## 14. 데이터 모델 (`models.py` 스케치, R19 — 누락 보완)

```python
class MarketRegimeResult(BaseModel):
    regime: str; allow_new_buy: bool; index_symbol: str; detail: str

class RelativeStrengthResult(BaseModel):
    mansfield_rs: float; outperform_6m: float; rp_slope_4w: float
    is_strong: bool; index_symbol: str

class SectorStrengthResult(BaseModel):
    industry: str | None; rank_pct: float | None; trend: str
    is_strong: bool | None; source: str

class VcpResult(BaseModel):
    in_vcp: bool; pivot: float | None; breakout: bool; detail: str

class AccumulationResult(BaseModel):
    accumulation_days: int; distribution_days: int
    accumulation_ratio: float; pocket_pivot: bool

class ElementVerdict(BaseModel):
    met: bool | None; detail: str

class CanslimResult(BaseModel):
    c: ElementVerdict; a: ElementVerdict; n: ElementVerdict; s: ElementVerdict
    l: ElementVerdict; i: ElementVerdict; m: ElementVerdict
    score: int; summary: str

class GateCheck(BaseModel):
    name: str; required: bool; met: bool | None; reason: str

class GateResult(BaseModel):
    passed: bool; checklist: list[GateCheck]
    quality_grade: str | None; veto_reason: str | None

class PositionPlan(BaseModel):
    entry: float; stop: float; stop_basis: str; per_share_risk: float
    shares: int | None; position_value: float | None; weight_pct: float | None
    r_targets: dict[str, float]; capital_mode: str; error: str | None

class ExitSignal(BaseModel):
    code: str; severity: str; detail: str

class ExitVerdict(BaseModel):
    action: str; signals: list[ExitSignal]
    current_r: float | None; trailing_stop: float | None; detail: str

class PlaybookVerdict(BaseModel):
    ticker: str; holding: bool
    market_regime: MarketRegimeResult
    relative_strength: RelativeStrengthResult
    sector_strength: SectorStrengthResult | None   # R19 — 추가
    canslim: CanslimResult
    gate: GateResult | None
    position_plan: PositionPlan | None
    exit_verdict: ExitVerdict | None
    headline: str
```

`AnalyzeDecisionSummary` 추가(R17): `action_original: str | None`, `veto_applied: bool`.

> `PlaybookVerdict`는 코드가 dict에 주입(LLM structured output 아님) → strict schema 무관. LLM 입력 주입은 프롬프트 텍스트로만.

---

## 15. 출력 형식 (CLI)

```
📋 플레이북 평가  [AAPL · 미보유]
판정: ✅ 신규진입 적격 (품질 B)        ← 또는 ❌ 부적격: {veto_reason}
체크리스트(★):
  A 시장환경   ✅ S&P500 상승추세
  B Stage 2    ✅ Is_Stage2=true
  C 종목+업종  ✅ 종목 RS +12.3 / 업종 Semiconductors 상위 12% (업종 내 순위 미검증)
  E 셋업       ⚠️ VCP 수축, 피벗 돌파 미확인
가점:
  CANSLIM      C✅ A✅ N✅ S⚠️ L✅ I✅ M✅ (6/7)
  기관(거래량) ✅ 매집일 14/22, Pocket Pivot
포지션 플랜 (위험 1% · 30,000 USD):
  진입 $195.0 / 손절 $181.4 (−7.0%, 구조무효화) / 1R=$13.6
  수량 22주 · 14.3% · +2R $222 / +3R $236
```
한국 종목: `C 업종 — KIS 업종지수`, `RS/평단 — 수정주가 적용`.

---

## 16. 데이터 가용성 (v3)

| 항목 | 미국 | 한국 | 처리 |
|---|---|---|---|
| 지수 추세 / 종목 RS | ✅ | ✅ | IndexProvider |
| 분기 EPS증가율 (C) | ✅ EPS | ✅ **순이익**(EPS 가용 시 EPS) | growth-ratio div_cls=1 (R20) |
| 업종 강도 (C★ 필수) | ✅ FMP(historical 플랜 게이팅) | ✅ KIS 업종지수 (R26) | 매핑 실패 시 종목 RS graceful |
| 기관(거래량 I) | ✅ | ✅ | volume/accumulation |
| 가격 수정주가 | (yfinance 자동) | ✅ 적용 | D1 |

---

## 17. 테스트 전략
- 순수 함수 단위: gate/sizing/exit_rules/market_regime/relative_strength/sector_strength/vcp/canslim/accumulation + **apply_playbook_veto**(R17).
- 골든: (1)Stage2 적격 (2)★탈락 (3)보유 청산 (4)★ None 보수적 부적격.
- 사이징: 1000만·1%·5만/4.75만→40주. `per_share_risk≤0`·상한가드.
- Stage2: `is_stage2`가 `Is_Stage2` 컬럼과 일치(단일 출처 검증, R16).
- C: growth-ratio mock에서 **EPS 필드 유무 분기**(EPS / 순이익 fallback, R20).
- sector_strength: 업종명 매칭 실패 → None, 한국 → skip, historical 없음 → snapshot-only.
- 수정주가: 적용 전후 RS/52주 회귀(D1).
- 외부 API mock; 실호출 `integration` 마커.

---

## 18. 미해결 / 추후
- IBD 백분위 RS Rating + **업종 내 주도주 1~2등** → `screen` 유니버스.
- 한국 업종 강도: KRX 업종지수/naver 연동.
- 피라미딩, 시장 distribution day 천장 경고, 매매 일지.

---

## 19. 구현 순서
1. `IndexProvider` + `FmpProvider`(미국 업종명 매핑) + `holdings.py` + `models.py`(§14)
2. `kis.py`: div_cls 인자화 + `get_growth_ratio` + **수정주가 적용** + **업종지수 API 3종 + 종목→업종 매핑**(R26) + **분기/EPS 필드/수정주가/업종 실호출 검증**(R18, R20, D1, R26)
3. `fundamental.py`: `annual_data`/`eps_yoy` + LLM입력/CLI렌더
4. `indicators._calculate_stage2`·`Is_Stage2` 제거(D5) + `minervini.py`가 7조건 판정 → `metrics["is_stage2"]` (R16, D4, D5) — 단일 출처
5. `market_regime`+`relative_strength`+`sector_strength`(**C★ 필수, FMP+KIS 2구현**)+`vcp`(돌파)+`accumulation`
6. `canslim` + `gate` + `sizing` + `exit_rules`
7. `engine`(§4.2 순서) + `apply_playbook_veto`
8. `deep_dive`/`analyze_decision`/`main.py` 연결 + 수정주가 회귀 테스트
9. 단위·골든 테스트

---

## 20. 엣지케이스
- **코스피/코스닥 판별**: `.KS`→`^KS11`, `.KQ`→`^KQ11`. 6자리만 → KIS 시장코드 또는 `^KS11` fallback+경고.
- **한국 수정주가 (D1)**: `get_price_history` `FID_ORG_ADJ_PRC` 수정주가 적용. RS(252일 RP)·매집·평단·52주 정확도 향상. **기존 quick_check/deep_dive 기술분석 회귀 검증 필수**(분할·배당 종목 골든 케이스).
- **한국 업종(C★)**: KIS 업종지수로 지원(R26). 종목→업종 매핑 실패 시 → `is_strong=None` → 종목 RS만으로 C 판정(§6.3 graceful). KRX 업종 분류가 GICS보다 거침에 유의.
- **통화 환산**: 종목 통화에 맞는 account(미국→usd). 없으면 비율 모드.
- **신규 상장/짧은 히스토리**: 200/252/50일 미달 → 해당 ★ None → §6.3 보수적 부적격.
- **업종명 매칭 실패**: yfinance↔FMP 불일치 → `is_strong=None`(R24).
