# 기능 명세

> 이 문서는 시스템의 **현재 상태**를 기술합니다. 기능 변경 시 이 문서를 함께 업데이트하세요.
> 변경의 **이유**는 `docs/adr/`에 별도 기록합니다.
> 브레인스토밍/설계 탐색 결과는 `docs/superpowers/specs/`, PR 단위 변경 기록은 `docs/changes/`에 둡니다.

---

## 1. Quick Check (`jarvis check`)

LLM 없이 기술적 분석만 수행하는 빠른 진단 기능.

**입출력:**
- 입력: 티커 또는 종목명 (TickerResolver로 자동 변환)
- 출력: 8개 컴포넌트 점수, context 조정 점수, technical verdict, 최근 점수 추이, 시그널, 경고, 20+ 원시 지표, 퍼포먼스 (1M/3M/6M/1Y)

**기술 점수 계약:**

- `total_score`와 `component_raw_total`은 8개 컴포넌트 raw 합계를 유지한다.
- `adjusted_score`는 `MarketContext`와 structured signal metadata를 반영한 조정 점수다. raw OHLCV 별도 score는 만들지 않는다.
- `technical_verdict`는 `buy/add/hold/watch/reduce/avoid` 중 하나의 technical-only hint와 판단 이유, 주의점, 무효화 가격, 최근 5거래일 점수 추이를 제공한다.
- LLM은 확정된 score와 verdict를 재판단하지 않고 한국어로 설명만 한다.

**8개 기술적 컴포넌트:**

| 컴포넌트 | 역할 |
|----------|------|
| Minervini | 추세 추종 (20/50/150/200일 이평선 배열) |
| Velocity | 가격 모멘텀 및 가속도 |
| CRSI | 과매수/과매도 (Cycle RSI) |
| Volume | 거래량 추세, 평균 대비 비율, Pocket Pivot, Tennis Ball/Egg, Power Gap Up |
| Patterns | VCP 2-Stage, Breakout (신고가/스윙), Candlestick (Hammer, Bullish Engulfing) |
| Supertrend | ATR 기반 추세 감지 |
| Divergence | RSI/MACD 다이버전스 |
| Risk | 최대 낙폭, 변동성 |

**Volume 컴포넌트 상세:**

| 패턴 | 조건 | 점수 | 설명 |
|------|------|------|------|
| **Pocket Pivot** | 다운데이 거래량 > 10일 최대 + 50일선 ±2% | 25 | 기관 매집 신호 (Gil Morales) |
| **Tennis Ball** | 하락 거래량 < 50% 평균 | 15 | 평균회귀 반등 가능성 |
| **Egg** | 하락 거래량 > 150% 평균 | -15 | 추가 하락 리스크 (첫 negative score!) |
| **Power Gap Up** | 갭 ≥4% + 거래량 3x | 20 | 강세 갭업 |
| 거래량 급증 | 거래량 2x + 가격 상승 | 15 | 기존 로직 유지 |

**Patterns 컴포넌트 상세:**

| 패턴 | 조건 | 점수 | 설명 |
|------|------|------|------|
| **VCP Strong** | ATR 수축 20% + Tight days 5/20 + 최근 3일 연속 | 20 | Mark Minervini VCP 2-Stage |
| **VCP General** | ATR 수축 20% 이상 | 10 | 단계 1만 만족 |
| **Breakout** | 20일 신고가 or 스윙 고점 돌파 | 20 / 10 | 가격 돌파 |
| **Hammer** | 아래 꼬리 > 몸통 × 2 | 10 | 하단 지지 신호 |
| **Bullish Engulfing** | 양봉이 이전 음봉 포함 | 15 | 반전 신호 |

**의존성:** yfinance (가격 데이터)

---

## 2. Deep Dive Analysis (`jarvis analyze`)

기술적 분석 + 펀더멘탈 + 뉴스 + 공시 + 수급을 종합해 판단 우선 요약과 투자 해석을 생성.

**입출력:**
- 입력: 티커 (분석 모델은 config.yaml `llm.analyze` 섹션에서 설정)
- 출력: 판단 요약(주도 팩터, 핵심 변수, 액션, 보류 이유), 액션 시나리오, 원시 분석

**분석 레이어:**

| 레이어 | 데이터 소스 | LLM 출력 |
|--------|-----------|----------|
| 기술적 | **KIS API (한국) / yfinance (미국)** → 8개 컴포넌트 | TechnicalSummaryOutput |
| **패턴** | OHLC → 9개 차트 패턴 | ChartPatternResult |
| **가격 레벨** | 6개 소스 (MA, Fib, Pivot, Swing, ATR, Pattern) | PriceLevels |
| **구조 레벨** | 3년 가격 CSV/실시간 OHLC → 수요/공급 zone + 무효화 후보 | StructureZoneSet |
| 펀더멘탈 | **KIS 재무 API 5종 (한국) / yfinance (미국)** | FundamentalSummaryOutput |
| 뉴스 | yfinance 뉴스 | NewsAnalysisOutput |
| 공시 | SEC EDGAR / OpenDART (선택) | - |
| 수급 | KIS API (한국주식 전용) | - |
| **Macro** | VIX·F&G·금리·DXY·WTI (Analyze/Brief 전용) | TickerMacroSnapshot |
| **종합 해설** | 위 전체 + 규칙이 확정한 decision 설명 (새 액션/타이밍 생성 안 함) | IntegratedExplanationOutput |

**데이터 소스 자동 선택:**
- 한국 주식 (`.KS`, `.KQ`) 감지 시 → KIS API 사용 (실시간)
- KIS API 키 없으면 → yfinance로 자동 fallback (3일 지연 가능)
- 미국/글로벌 주식 → yfinance 사용

**판단 우선 요약 규칙:**
- 상단 `핵심 변수`는 장문 요약이 아니라 짧은 headline 라벨 2개만 노출
- 기술 팩터는 `technical_verdict`가 있으면 이를 우선 반영하고, 없을 때만 기존 `total_score` 기반 판단으로 fallback
- LLM technical summary는 `technical_verdict`, 최근 `score_history`, aggregation trace를 fixed rule facts로 받아 설명
- `혼합` 구간에서는 가격 팩터를 약간 우선해 핵심 변수를 정렬
- 오래된 차트 패턴은 headline이 아니라 상세 이유에서 감점 근거로 설명
- 한국 주식 재무 지표가 부족하면 밸류 판단을 유보하고 원시 지표는 `N/A`로 표시
- 액션 시나리오는 `최근 지지/저항 + 50일선 + 150일선 + 무효화 레벨` 구조로 출력
- 구조 레벨은 `수요 존 / 공급 존 / 무효화 기준`을 zone 중심으로 분리 출력
- 실행 레벨은 pivot / MA / fib / ATR 중 가까운 line 위주로 3개만 노출

**KIS 재무 조회 복원력:**
- 한국 주식 재무 API 5종은 엔드포인트별 재시도(최대 3회) 적용
- 일부 엔드포인트 실패 시에도 성공한 엔드포인트 데이터로 펀더멘털 스냅샷 생성
- 전체 엔드포인트가 모두 실패한 경우에만 펀더멘털 섹션을 실패 처리

**KIS Provider 확장 (Plan 1):**
- 재무 API 메서드 6종에 `div_cls_code` 인자 추가: `"0"`=연간(기본), `"1"`=분기
- `get_growth_ratio` 신규: `/finance/growth-ratio` (tr_id FHKST66430800) — 매출/영업이익/순이익 증가율
- `get_price_history` 기본값을 수정주가(`ADJUSTED="0"`)로 변경 — 액면분할 왜곡 방지 (2026-06 실호출로 `"0"`=수정주가 확정)

**차트 패턴 감지 (Phase 2):**

기존 패턴 (임계값 완화):
| 패턴 | 기간 | 신뢰도 가중치 | 설명 |
|------|------|---------------|------|
| Cup & Handle | 40-120일 | 깊이/기간 차등 | 컵 15-40%, 손잡이 <15%, 최소 50일 |
| Double Bottom | 20-80일 | 기간 차등 (0.85/0.95) | 바닥 간 <5%, 최소 50일 |
| Head & Shoulders | 40-100일 | - | 어깨 높이 <10%, Head >3%, 최소 50일 |

신규 패턴 (Phase 2 추가):
| 패턴 | 기간 | 신뢰도 가중치 | 설명 |
|------|------|---------------|------|
| Ascending Triangle | 30-90일 | 수평/기울기/수렴 기반 | 수평 저항 + 상승 지지, 돌파 시 상승 기대 |
| Descending Triangle | 30-90일 | 수평/기울기/수렴 기반 | 수평 지지 + 하락 저항, 하락 돌파 시 추가 하락 |
| Bullish Flag | 최소 30일 | Pole 강도 기반 | 강한 상승 (>10%) + 하락 조정, 재상승 기대 |
| Bearish Flag | 최소 30일 | Pole 강도 기반 | 강한 하락 (>10%) + 상승 조정, 재하락 기대 |
| Support Level Test | 최근 60일 | 테스트 횟수/범위/반등 기반 | 3회 이상 같은 가격대(6% 범위) 테스트, 강한 지지선 확인 |

기타 패턴:
| 패턴 | 기간 | 설명 |
|------|------|------|
| Support/Resistance Test | 최근 20일 | ±2% 레벨 근처 |

**버그 수정:**

- **2026-04-25: CRITICAL - High/Low 가격 데이터 사용**
  - 기존 문제: 모든 패턴이 Close 가격만 사용하여 peaks/valleys를 부정확하게 감지
  - 수정 내용:
    - Cup & Handle, Head & Shoulders: High 가격으로 peaks 감지
    - Double Bottom: Low 가격으로 valleys 감지
    - Triangle 패턴들: High/Low 가격으로 peaks/valleys 감지
  - 영향: 실제 시장 데이터에서 누락되던 패턴들이 정상적으로 감지됨
  
- **2026-04-25: Double Bottom 개선 - 최근 패턴 우선**
  - 기존 동작: 첫 번째로 발견된 패턴만 리턴
  - 개선 내용: 모든 유효 패턴을 찾아 가장 최근 패턴(days_ago가 가장 작은 것) 리턴
  - 장점: 오래된 패턴보다 최근 패턴이 투자 의사결정에 더 유용

- **2026-04-27: Supertrend 차트 시각화 버그**
  - 기존 문제: Supertrend 라인 대신 Close 가격을 direction에 따라 색칠
  - 수정 내용: SUPERT_10_3.0 라인 값을 direction에 따라 녹색/빨간색으로 표시
  - 영향: 차트에서 Supertrend 라인 위치가 정확하게 표시됨 (가격 위: 녹색, 가격 아래: 빨간색)

- **2026-04-27: 차트 컬럼 이름 불일치 버그**
  - 기존 문제: DataFrame 컬럼(SMA_20, MACD_12_26_9 등 대문자)과 차트 코드(sma_20, macd 등 소문자) 불일치
  - 수정 내용: 차트 코드의 모든 컬럼 참조를 DataFrame 실제 이름으로 변경
  - 영향: MA, Supertrend, MACD, RSI, Volume 등 모든 지표가 차트에 정상 표시됨

- **2026-04-27: KIS API 100일 제한 해결 (MA200 필수)**
  - 기존 문제: KIS API가 한 번에 100일만 반환하여 MA200 계산 불가
  - 수정 내용:
    - 100일씩 3번 호출로 200+ 일 데이터 수집 (batch 방식)
    - 파일 기반 토큰 캐싱 (~/.cache/invest-jarvis/kis_token.yaml)
    - 3-tier 캐싱: 메모리 → 파일 → API (1분 rate limit 회피)
    - 차트 window_days를 63 → 200일로 확장
    - KIS API 인증 전처리 (실패 시 즉시 중단, fallback 없음)
  - 영향: 
    - 한국 주식 208일 데이터 수집 성공
    - MA200 라인 정상 표시
    - 토큰 재발급 1분 제한 회피

- **2026-04-27: 차트 지표 컬럼 필터링 버그**
  - 기존 문제: TechnicalData.from_analysis()가 OHLCV + 일부 지표만 저장하여 차트에 MACD/RSI/Supertrend 미표시
  - 원인: indicator_cols 필터가 "SMA_", "sma_", "vol_sma_", "supertrend_direction"만 포함
  - 수정 내용: 필터에 "MACD", "RSI", "SUPERT", "Vol_SMA_" 패턴 추가
  - 영향: 
    - MACD 패널 (MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9) 정상 표시
    - RSI 패널 (RSI_14) 정상 표시
    - Supertrend 라인 (SUPERT_10_3.0) 정상 표시
    - 거래량 이평선 (Vol_SMA_20) 정상 표시

**가격 레벨 분석 (Phase 2):**

| 소스 | 포함 레벨 | 우선순위 |
|------|----------|---------|
| MA | 20/50/150/200일 | 3 (높음) |
| Swing | High/Low | 3 (높음) |
| Pivot | S1/R1 | 2 (중간) |
| Fibonacci | 9개 (0.236~2.0) | 1 (낮음) |
| ATR | 1x/2x 지지/저항 | 0 (최하) |
| Pattern | 돌파 레벨 + 목표가 | 패턴 신뢰도 기반 |

- 중복 제거: 현재가 ±5% 내 0.5% threshold, 그 외 1.0%
- 정렬: 지지선 높은 순, 저항선 낮은 순 (가까운 것 우선)
- 출력: 각각 상위 5개 + 패턴 타겟

**구조 레벨 분석 (Structure Zone):**

| 항목 | 규칙 |
|------|------|
| 입력 | 장기 OHLCV (기본 3년 fixture 또는 실시간 조회) |
| 후보 추출 | swing high / low cluster |
| zone 폭 | ATR 기반 폭, 최소/최대 % floor/ceiling 적용 |
| 점수 | touch / recency / volume reaction / confluence 가중 합 |
| 출력 | 수요 존 2개, 공급 존 2개, 무효화 기준 1개 |

- 구조 레벨은 장기 구조 판단용 zone이다.
- 실행 레벨은 단기 진입/확인/리스크 관리용 line이다.
- `jarvis analyze`는 두 레이어를 모두 LLM 프롬프트와 CLI 출력에 전달한다.

**Actionable Signal Output (Phase 2 확장):**

기존 필드 (Phase 1):
- `action` (매수/매도/관망), `timing` (지금/조정_대기/보류)
- `signal_strength` (1-10), `headline`, `primary_reason`
- `supporting_reasons`, `risks`, `invalidation_point`, `confidence`

신규 필드 (Phase 2):
- `pattern_insight`: 차트 패턴 해석 (예: "Cup & Handle 8일 전 완성, 돌파 준비")
- `target_price`: 가격 목표 자유 서술 (예: "돌파 시 $250, 조정 시 $175 지지")
- `entry_zone`: 진입 구간 (예: "현재 $200 횡보, 조정 시 $175-180 매수")
- `key_levels`: 주요 레벨 요약 (예: "지지: $187/$175, 저항: $200/$250")

**차트 시각화:**

Deep Dive 분석 실행 시 자동으로 기술적 차트를 생성하여 `charts/` 디렉토리에 저장합니다.

| 항목 | 내용 |
|------|------|
| **렌더 엔진** | mplfinance (matplotlib 기반) |
| **출력 파일** | `charts/{ticker}_technical.png` |
| **해상도** | 130 DPI |
| **패널 구조** | 4개 패널 (비율 6:2:2:2) - Price, Volume, MACD, cRSI |
| **기간** | 최근 63일 (약 3개월) |
| **한글 지원** | 한국어 폰트 자동 감지 (Noto Sans KR, AppleGothic 등) |
| **자동 열기** | macOS/Linux에서 차트 자동 표시 (open/xdg-open) |

**가격 패널 (Panel 0):**
- 캔들스틱
- **6개 이동평균선** (우선순위별 스타일링):
  - MA50 (#00D1FF, width=3.0) - 최고 강조
  - MA200 (#FF2D55, width=2.8)
  - MA120 (#FF8C00, width=2.0)
  - MA20 (#4DA3FF, width=1.8)
  - MA10 (#B0B0B0, width=1.0) - 참고용
  - MA150 (#8A8A8A, width=0.9) - 참고용
- **Supertrend 추세선**:
  - 상승 추세: SuperTrend_Up (초록, width=2)
  - 하락 추세: SuperTrend_Dn (빨강, width=2)
  - 매수/매도 전환 시그널 마커 (markersize=35)
- **Stage2 음영**: Minervini Stage2 조건 충족 구간 (초록 배경, alpha=0.08)
- **차트 패턴 마커**: 검출된 패턴 위치에 화살표 + 라벨 표시
- **지지/저항선**: 지지선(녹색 점선), 저항선(빨간색 점선) 각 최대 3개
- **우측 MA 라벨**: 6개 MA의 현재 값 표시 (색상 코딩)

**거래량 패널 (Panel 1):**
- 거래량 막대 (mplfinance 기본)
- Volume MA50 오버레이 (골드 라인)
- 라벨: "VOL + VOL_MA50"

**MACD 패널 (Panel 2):**
- MACD 히스토그램 (회색, alpha=0.55)
- MACD 라인 (파랑)
- Signal 라인 (주황)
- 라벨: "MACD(12,26,9)"

**cRSI 패널 (Panel 3):**
- cRSI 라인 (마젠타)
- 동적 밴드 (청록, 10th/90th percentile over 40-bar lookback)
- 30/70 참조선 (회색 점선)
- 라벨: "cRSI(dc=20,vib=10,lvl=10%)"

**Helper 함수:**
- `_setup_korean_font()`: macOS/Linux 한글 폰트 설정
- `_badge()`: 패널 레이블 표시
- `_shade_stage2()`: Stage2 배경 음영 그리기
- `_right_value_labels()`: 6개 MA 라인 우측 값 표시
- `_draw_support_resistance()`: 지지/저항선 그리기
- `_mark_patterns()`: 패턴 완료 지점 마킹

**의존성:** yfinance, LLM (OpenAI/Anthropic), scipy (peak detection), mplfinance, SEC EDGAR, OpenDART (선택), KIS API (선택)

---

## 3. Daily Brief (`jarvis brief`)

로컬 `playbook.yaml`의 보유 종목과 워치리스트를 평가해 일일 액션 브리핑을 생성.

**입출력:**
- 입력: `playbook.yaml`의 `holdings` + `watchlist`
- 출력: 터미널 마크다운 + `reports/YYYY-MM/brief_YYYY-MM-DD.md`

**평가 흐름:**
- `PlaybookEngine.evaluate()`로 보유/워치 종목의 액션 판정
- 버킷 랭킹으로 청산/매수 가능/축소/진입 임박/관망 후보 우선순위 정렬
- 뉴스·공시·수급은 점수에 반영하지 않고 근거 표기에만 사용
- LLM은 종목별 서술 슬롯 문장화만 담당하며 `--no-llm` 실행 가능

**데이터 소스:** TechnicalAnalysisTool, PlaybookEngine, MacroTool, NewsTool, DisclosureTool, FlowTool

---

## 4. Market Screener (`jarvis screen`)

한국/미국 시장에서 모멘텀 기반 선도주를 스캔.

**3단계 워크플로우:**

| 단계 | 역할 | 데이터 소스 |
|------|------|-----------|
| Universe Building | 종목 후보 수집 | Naver 테마/순위 (KR), yfinance (US) |
| Evidence Scoring | 모멘텀 스코어링 | 기술 지표, 거래량, 수급 (KR) |
| Theme Aggregation | 테마별 그룹핑 + 랭킹 | 위 결과 집계 |

**출력:** 테마 Top 10 + 종목 Top 50 (KR/US 각각) + 뉴스

**Notion 업로드 (선택):**
- `--notion` 옵션으로 Screener 리포트를 Notion Database에 업로드
- 통합 Database 구조 (Type: Screener)

**의존성:** Naver API, yfinance, KIS API (선택), Notion API (선택)

---

## 5. Daily Report Pipeline (`jarvis report daily`)

텔레그램 채널 메시지를 5단계 MapReduce로 분석하여 일일 시장 리포트 생성.

**5단계 파이프라인:**

| Stage | 역할 | LLM | 입력 → 출력 |
|-------|------|-----|------------|
| **Ingest** | 메시지 + 매크로 로드 | X | CSV → IngestResult |
| **Map** | 이슈 추출, 카테고리 분류 | gpt-5.6-luna (temp 0.2) | messages → MappedIssue[] |
| **Shuffle** | 카테고리 그룹핑 + 테마 정규화 | gpt-5.6-luna (temp 0.1) | issues → ShuffleResult |
| **Reduce** | 테마별 분석 리포트 | gpt-5.6-terra (temp 0.3) | theme groups → NewsItem[] |
| **Wrapup** | 크로스 테마 인사이트 | gpt-5.6-terra (temp 0.4) | news items → DailyReport |

**Map Stage 동작:**
- 유사 메시지를 하나의 이슈로 클러스터링 (같은 기업/산업 트렌드/인과관계/복수 종목)
- avg_sources < 1.7 시 품질 경고 로그 출력
- 같은 투자 내러티브는 같은 테마명 재사용

**Shuffle Stage 동작:**
- 카테고리 내 테마 정규화 시 issue 제목 컨텍스트 활용
- 밸류체인/인과관계 기반 테마 통합

**데이터 모델:**

```
TelegramMessage → MappedIssue → ShuffleResult → ThemeAnalysis/NewsItem → DailyReport
```

| 모델 | 역할 |
|------|------|
| `MacroSnapshot` | VIX, CNN Fear & Greed, KRW/USD, 미국/한국 시장 변동률 |
| `MappedIssue` | 카테고리(18종), 제목, 요약, 테마(1-3), 감성(Sentiment enum), 소스 ID |
| `ThemeAnalysis` | Reduce LLM 출력 (category 제외): 투자 테마명, 검색 키워드, 이모지, 요약, 임팩트, 관련종목 |
| `NewsItem` | ThemeAnalysis + category + technical_theme + source_ids (원본 메시지 추적용) |
| `DailyReport` | 날짜, 매크로, 핵심 인사이트, 테마별 뉴스 |

**18개 고정 카테고리:**
반도체, 디스플레이, 이차전지, 소재/화학, 자동차, 조선/중공업, 방산, AI/소프트웨어, 통신, 바이오/제약, 유통/소비재, K-푸드, 에너지, 건설/부동산, 금융/보험, 매크로, 정책/규제, 기타

**설정 (`config.yaml` `llm.daily` 섹션):**

| 스테이지 | 모델 | temperature | 용도 |
|----------|------|-------------|------|
| map | gpt-5.6-luna | 0.2 | Map 스테이지 |
| shuffle | gpt-5.6-luna | 0.1 | Shuffle 스테이지 |
| reduce | gpt-5.6-terra (defaults 상속) | 0.3 | Reduce 스테이지 |
| wrapup | gpt-5.6-terra (defaults 상속) | 0.4 | Wrapup 스테이지 |

모든 스테이지의 provider 기본값은 `openai`. 모델·temperature는 `config.yaml` `llm.daily`에서 오버라이드 가능.

| 상수 | 값 | 용도 |
|------|---|------|
| `MAP_MAX_TOKENS_PER_CHUNK` | 80,000 | Map 청크 크기 |
| `LLM_TIMEOUT_SECONDS` | 180 | LLM 호출 타임아웃 (Map 100+ 메시지 대응) |
| `LLM_MAX_RETRIES` | 3 | LLM 재시도 (exponential backoff) |
| `MACRO_MAX_RETRIES` | 3 | 매크로 데이터 재시도 |

**매크로 데이터:**
- 미국/한국 시장 지수 변동률 (yfinance)
- VIX (yfinance)
- Fear & Greed Index (CNN `fear-and-greed` 패키지)
- KRW/USD 환율 (yfinance)
- 모든 항목 3회 리트라이 (exponential backoff)

**프롬프트 캐싱:**
- 스테이지의 provider가 `anthropic`일 때 system prompt에 `cache_control: ephemeral` 자동 적용
- provider가 `openai`(기본값)이면 자동 비활성화 (`StageLLMConfig.build_messages()`)

**리포트 출력:**
- Markdown 파일: `reports/YYYY-MM/daily_YYYY-MM-DD.md`
- 각 테마마다 **출처** 섹션에 원본 메시지 발췌 포함
- source_ids로 CSV에서 원본 메시지 로드 → keywords 매칭 시 주변 ~200자 발췌, 매칭 없으면 전체 메시지
- **포맷**: 개행문자 변환, 출처에 채널명+인용블록, 테마 구분선(`---`)

**의존성:** 텔레그램 CSV, OpenAI (gpt-5.6-luna/gpt-5.6-terra), yfinance, fear-and-greed

---

## 5-1. Stock Report V2 Pipeline (`jarvis report daily-v2`)

텔레그램 CSV를 message 단위로 정규화하고 LLM semantic extraction 결과를 Postgres 기반 knowledge chunk로 적재하는 차세대 일일 리포트 엔진.

**현재 범위:**
- `gpt-5.4-mini` 기반 semantic extraction으로 report unit 생성
- `category_key/main_theme/sub_themes/event_type/canonical_summary/supporting_facts` 구조화
- 런타임 taxonomy overlay로 `provisional_category/provisional_theme` 보강
- `knowledge_chunks` 적재 및 grouped-only chunk 생성
- 날짜별 DB 적재 결과를 메시지 단위로 조회하는 `scripts/stock_report_show_chunks.py` 제공
- map-reduce 종합: 카테고리/티커별 LLM consolidation(중복 채널 병합) → reduce로 Pulse/Core Themes 생성, LLM 실패 시 결정적 raw 카드로 graceful fallback
- 결정적 high-impact 이벤트 안전망: `event_type ∈ {M&A, 자본조달}` 청크를 LLM이 누락해도 카테고리 카드에 강제 보강 (`event_safety_net.py`) — 프롬프트로 못 잡는 nondeterministic 누락 방지

**저장소:**
- 개발 환경은 로컬 Docker Postgres + pgvector 이미지 사용
- `STOCK_REPORT_DB_DSN`이 있으면 DB 적재를 수행하고, 없으면 preview 중심으로 실행

**제약:**
- `supporting_facts`는 아직 flatten된 근거 리스트이며, 향후 typed evidence layer로 세분화 예정
- `provisional_*` 값은 taxonomy 정제 전 당일 리포트 품질을 위한 임시 보강값

---

## 5-2. Stock Report V2 - PDF Ingest (`jarvis report ingest-pdf`)

증권사 PDF 리포트를 파싱·청킹·임베딩하여 `documents`/`document_chunks`에 적재하는 RAG 인제스트 파이프라인 (V2 Phase 2).

**현재 범위:**
- `opendataloader-pdf`(Java) 기반 PDF → Markdown 파싱, local/hybrid 2개 모드 + 재무 라벨 융합 증상 시 `needs_hybrid` 승격 라우팅
- small-to-big 청킹: 산문은 작은 청크, 표는 원자 청크, `section_path`로 부모 섹션 복원
- 2-패스 적재: 청크를 `embed_status='pending'`으로 먼저 커밋한 뒤 임베딩을 DB 트랜잭션 밖에서 별도 처리 (임베딩 실패 시 pending 보존·재시도)
- `text-embedding-3-small`(1536차원) 임베딩 → pgvector HNSW cosine 검색
- 멱등성: 같은 경로의 `content_hash` + `parser_version`이 동일하면 재파싱 skip
- 중복 차단: 같은 내용(`content_hash`)이 다른 경로로 들어오면 skip (배치 내·DB 모두, `--reembed`와 무관하게 항상 적용)
- 노이즈 필터: 차트 파이프블록·잔여 `<br>`·의미 단어 0개 청크 제거
- 문서 분류: taxonomy 기반 LLM 분류로 `category_key`/`main_theme` 부여(텔레그램과 같은 카테고리 체계). LLM 실패/미정 시 alias 규칙 매칭 fallback
- 티커 추출: 제목 헤딩에서 한국 6자리·해외 `TICKER.EX`(숫자 시작 중국 코드 `300308.CH` 포함) 추출

**청킹 품질 (CP3):**
- 단편 병합(`_merge_short_chunks`): `MIN_CHARS`(200자) 미만 산문 조각을 다음 청크 앞에 prepend. 표·출처줄은 제외. 완결 문장(`.!?。…` 종결)은 짧아도 보존해 정상 본문 오병합 방지
- 병합 후 `embed_payload` 재생성: 제목·캡션 키워드가 임베딩에 반영되도록 보장
- 노이즈 필터와 소스줄 필터 사이에 실행되어 단편 흡수 → 출처줄 필터 순서 유지

**검색 (`search_document_chunks` / `search_documents`):**
- CTE + `ROW_NUMBER() OVER (PARTITION BY document_id)` per-document dedup: 동일 문서가 top-K를 독점하지 않도록 문서당 최고 유사도 1개만 반환
- `category_filter`(카테고리)·`ticker_filter`(`ticker_tags @>` exact 태그)로 검색 범위 한정, AND 결합
- `search_documents(query_text, ...)`: 텍스트 쿼리를 임베딩해 검색하는 래퍼(T17 synthesis LLM 툴이 그대로 호출). 임베딩 키 부재/호출 실패 시 graceful 빈 결과
- `similarity` = `1 - (embedding <=> query_vec)` cosine 유사도 반환

**인증/엔드포인트 분리:**
- chat(분류/합성)은 사내 게이트웨이(`OPENAI_BASE_URL`)를 경유하지만, 게이트웨이가 임베딩 provider를 막는 경우가 있어 임베딩은 `OPEN_AI_EMBEDDING_KEY`(또는 `STOCK_REPORT_EMBED_API_KEY`)로 OpenAI 공식 엔드포인트를 직접 사용

**옵션:**
- `--input-dir`, `--use-hybrid`, `--ocr-lang`, `--embed-missing`(pending/failed 청크만 임베딩하는 backfill 경로), `--reembed`(멱등 skip 무시하고 전체 재적재) (분류 LLM은 config.yaml `llm.daily_v2.extraction` 설정을 따름)

**제약:**
- hybrid(docling) 통합은 `needs_hybrid=True` 문서 재처리 경로로 예정

---

## 5-3. Stock Report V2 - PDF Evidence via Tool-Calling (`jarvis report daily-v2`)

synthesis(map) 단계가 `search_documents`를 LLM tool로 직접 호출해 PDF 근거를 리포트에 통합하는 기능 (V2 T17).

**동작 방식:**
- `invoke_llm_with_tools` (`src/pipelines/stock_report/llm_tools.py`): `bind_tools` 루프(최대 2 round) → `asyncio.to_thread`로 동기 `search_documents` 호출 → 누적 history를 `with_structured_output` 최종 호출에 전달
- `search_fn` seam: `functools.partial(_search_documents, conn)`으로 connection-bound 함수 주입. `has_embed_auth()` false이면 `None` → 기존 텔레그램 전용 경로 그대로 동작 (100% 하위 호환)
- `ToolCallTrace`: 쿼리·category·ticker·top_k·hits를 라운드별 기록, `all_document_chunk_ids` dedup property로 중복 chunk 제거
- round cap: 미응답 `tool_calls`는 빈 `ToolMessage`로 정리 후 `with_structured_output` 호출 (OpenAI 400 방지)

**Evidence 격리 (B2/B3):**
- PDF 참조는 `_pdf_evidence_refs` 전용 경로만 사용 — `ReportSectionItem.evidence_chunk_ids`(텔레그램 공간)에는 절대 진입하지 않음
- `source_type='pdf'`, `evidence_kind='searched'` in `knowledge_chunk_snapshot`으로 DB에 기록

**저장:**
- `report_evidence` 테이블에 `source_type TEXT DEFAULT 'telegram'` 컬럼 추가 (migration `010_report_evidence_source_type.sql`)
- `document_chunk_id` 컬럼으로 PDF chunk ID 저장 (텔레그램 `knowledge_chunk_id`와 분리)
- `_dedup_evidence_refs`: `(section_key, item_key, knowledge_chunk_id, document_chunk_id)` 조합으로 중복 제거 후 적재

**렌더링:**
- `_build_source_lookup`: `source_type='pdf'` → `doc {id} {broker} · {title}` 형식, `telegram` → 기존 `chunk {id} {channel}#{msg}` 형식 (single dispatch)

**비용 상한:**
- major 버킷당 최대 3 round(2 tool + 1 final), `top_k=3`, `excerpt_chars=400`로 토큰 사용 상한 제한
- `has_embed_auth()=False`이면 PDF tool 호출 자체가 없어 기존 비용과 동일

---

## 6. Multi-ticker Quick Check (`jarvis check`)

여러 티커의 공통 3년 기술 분석을 LLM 없이 한 번에 확인한다.
(과거 티커 리포트의 기술 배치 역할을 대체 — 마이그레이션 경로는 change record 참고)

**입출력:**
- 입력: 티커 목록 (예: `jarvis check AAPL MSFT NVDA`)
- 출력: 종목별 8개 컴포넌트 점수 + technical_verdict (Macro 미포함)

**의존성:** yfinance / KIS API

---

## 7. Telegram Collection (`jarvis telegram`)

텔레그램 채널 메시지 수집 + 미디어 다운로드.

**두 가지 모드:**

| 모드 | 커맨드 | 동작 |
|------|--------|------|
| Fetch | `telegram fetch [날짜]` | 특정 날짜 메시지 전체 수집 |
| Catch-up | `telegram catch-up` | 마지막 수집 이후 누락분 보충 |

**채널 설정 (`config.yaml`):**
- `id`: 채널 식별자
- `timezone`: 메시지 날짜 기준 (Asia/Seoul 등)
- `include`/`exclude`: 정규식 필터

**출력:**
- CSV: `data/YYYY-MM/YYYY-MM-DD-{channel_id}.csv`
- 사진: `data/images/YYYY-MM-DD/{channel_id}_{msg_id}.jpg`
- 첨부 PDF: `data/files/YYYY-MM-DD/{channel_id}_{msg_id}_{filename}.pdf`
- URL PDF: `data/files/YYYY-MM-DD/{channel_id}_url_{msg_id}_{filename}.pdf`

**URL PDF 다운로드:**
- 메시지 본문에서 모든 HTTP(S) URL 추출
- HEAD 요청으로 Content-Type 확인 (follow_redirects=True)
- HEAD 실패 시(TooManyRedirects) GET으로 fallback (DART 등 HEAD 미지원 사이트 대응)
- 단축 URL(vo.la, bit.ly 등) 지원: 최종 리다이렉트 URL의 확장자도 체크

**의존성:** Telethon, httpx (미디어 다운로드)

---

## 8. Notion Integration

Daily Report 및 Screener 리포트를 Notion Database에 자동 업로드.

**명령어:**
- `jarvis report daily <날짜> --notion`: Daily Report 업로드
- `jarvis screen --notion`: Screener Report 업로드
- `jarvis report upload [날짜범위] [--type daily|screener|all]`: 기존 MD 파일 일괄 업로드

**Database 구조 (통합):**

| Property | Type | 용도 |
|----------|------|------|
| Name | Title | 리포트 제목 |
| Type | Select | Daily / Screener |
| Date | Date | 리포트 날짜 |
| Top Themes | Multi-select | 상위 5개 테마 |
| VIX | Number | VIX 지수 (Daily 전용) |
| Fear & Greed | Number | Fear & Greed Index (Daily 전용) |
| KRW/USD | Number | 원달러 환율 (Daily 전용) |
| Insights Count | Number | 핵심 인사이트 개수 (Daily 전용) |
| KR Leaders | Number | 한국 주도주 개수 (Screener 전용) |
| US Leaders | Number | 미국 주도주 개수 (Screener 전용) |

**마크다운 → Notion 블록 변환:**
- `**bold**` → Notion bold annotation
- Heading2, Divider, Callout, Table, Toggle 지원
- 테마별 분석: 이모지 + 투자 인사이트 테마명

**일괄 업로드:**
- `reports/` 디렉토리의 MD 파일 자동 파싱
- 날짜 범위 필터링
- 리포트 타입 필터 (daily/screener/all)
- 중복 방지 (Date + Type 기준)

**의존성:** notion-client

---

## 9. Ticker Resolution

종목명/티커 자동 변환 시스템. 모든 파이프라인에서 공통 사용.

**변환 우선순위:**
1. 정규식 직접 매칭 (AAPL, 005930.KS 등)
2. 로컬 캐시 조회 (6개월 TTL)
3. LLM Agent (GPT-4o + DuckDuckGo 검색)

**캐시:** `~/.cache/invest-jarvis/user_mappings.yaml`

---

## 10. Playbook Engine (`jarvis analyze` 통합)

5대 추세추종·모멘텀 대가(리버모어·터틀·오닐·와인스타인·미너비니) 규칙 기반 **매수 자격 게이트(veto) + 포지션 사이징 + 보유 매도 판정** 엔진. `analyze`의 `decision_summary`에 veto를 반영하고 "📋 플레이북 평가" 섹션을 출력. 설계: `docs/superpowers/specs/2026-06-10-playbook-engine-design.md`.

**구성 (`src/tools/playbook/`):**
| 모듈 | 역할 |
|------|------|
| `market_regime` | 지수(^GSPC/^KS11/^KQ11) 추세 게이트 (★A) |
| `minervini` Stage2 | 미너비니 추세 템플릿 7조건 (★B, 단일 출처) |
| `relative_strength` | 맨스필드식 종목 RS (★C, RS≠RSI) |
| `sector_strength` | 업종 강도: FMP(미국) + KIS 업종지수(한국) (★C 업종 / L) |
| `vcp` | VCP 피벗 돌파 (★E) |
| `accumulation` | 오닐식 매집/분산일 (I) |
| `canslim` | CAN SLIM 7요소 종합 (C·A·I 계산 + N·S·L·M 참조); CLI에서 7요소 각각 detail 출력 — S: vol_ratio(20일평균비), L: 업종명·순위·Mansfield·6M초과·4주기울기, M: 국면·지수심볼·판정근거 |
| `gate` | ★ A·B·C·E 필수(veto) + D·I·수급 가점 + 품질등급; B veto 사유에 `(N/7, 미충족: 조건명)` 형태로 Stage2 근접도 노출 |
| `sizing` | 손절 3후보(−8%/2×ATR/구조) + 위험% → 수량/R |
| `exit_rules` | 추세 종료 5신호 (보유 종목) |
| `engine` | 오케스트레이션 → `PlaybookVerdict` |
| `holdings` | `playbook.yaml` (account + holdings) |

**데이터:** 한국 분기/연간 EPS = `get_profit_ratio`(tr FHKST66430300, div=1/0), 가격 수정주가(`ADJUSTED="0"`), 업종 = FMP 업종 perf / KIS 업종지수. veto는 `apply_playbook_veto`로 `decision_summary` 후처리.

**의존성:** httpx, yfinance, FMP API, KIS API. **환경 변수:** `FMP_API_KEY`(미국 업종 강도; 없으면 업종은 graceful None).

---

## 환경 변수

| 변수 | 필수 | 용도 |
|------|------|------|
| `OPENAI_API_KEY` | 택1 | OpenAI LLM |
| `ANTHROPIC_API_KEY` | 택1 | Anthropic LLM |
| `KIS_APP_KEY` / `KIS_APP_SECRET` | 선택 | 포트폴리오, 수급 |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | 선택 | 텔레그램 수집 |
| `OPENDART_API_KEY` | 선택 | 한국 공시 |
| `NOTION_TOKEN` / `NOTION_DATABASE_ID` | 선택 | 리포트 업로드 |
| `FMP_API_KEY` | 선택 | 미국 업종 강도 (FMP) |
