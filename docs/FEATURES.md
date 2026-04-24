# 기능 명세

> 이 문서는 시스템의 **현재 상태**를 기술합니다. 기능 변경 시 이 문서를 함께 업데이트하세요.
> 변경의 **이유**는 `docs/adr/`에 별도 기록합니다.

---

## 1. Quick Check (`jarvis check`)

LLM 없이 기술적 분석만 수행하는 빠른 진단 기능.

**입출력:**
- 입력: 티커 또는 종목명 (TickerResolver로 자동 변환)
- 출력: 8개 컴포넌트 점수, 시그널, 경고, 20+ 원시 지표

**8개 기술적 컴포넌트:**

| 컴포넌트 | 역할 |
|----------|------|
| Minervini | 추세 추종 (20/50/150/200일 이평선 배열) |
| Velocity | 가격 모멘텀 및 가속도 |
| CRSI | 과매수/과매도 (Cycle RSI) |
| Volume | 거래량 추세, 평균 대비 비율 |
| Patterns | 캔들스틱 반전/연속 패턴 |
| Supertrend | ATR 기반 추세 감지 |
| Divergence | RSI/MACD 다이버전스 |
| Risk | 최대 낙폭, 변동성 |

**의존성:** yfinance (가격 데이터)

---

## 2. Deep Dive Analysis (`jarvis analyze`)

기술적 분석 + 펀더멘탈 + 뉴스 + 공시 + 수급을 LLM으로 종합하여 투자 추천을 생성.

**입출력:**
- 입력: 티커, LLM provider (openai/anthropic)
- 출력: 종합 추천 (매수/매도/중립), 근거, 리스크

**분석 레이어:**

| 레이어 | 데이터 소스 | LLM 출력 |
|--------|-----------|----------|
| 기술적 | yfinance → 8개 컴포넌트 | TechnicalSummaryOutput |
| **패턴** | OHLC → 4개 차트 패턴 | ChartPatternResult |
| **가격 레벨** | 6개 소스 (MA, Fib, Pivot, Swing, ATR, Pattern) | PriceLevels |
| 펀더멘탈 | yfinance (선택) | FundamentalSummaryOutput |
| 뉴스 | yfinance 뉴스 | NewsAnalysisOutput |
| 공시 | SEC EDGAR / OpenDART (선택) | - |
| 수급 | KIS API (한국주식 전용) | - |
| **종합** | 위 전체 통합 | IntegratedAnalysisOutput |
| **실행 시그널** | 기술 + 패턴 + 가격 레벨 | ActionableSignalOutput |

**차트 패턴 감지 (Phase 2):**

| 패턴 | 기간 | 신뢰도 가중치 | 설명 |
|------|------|---------------|------|
| Cup & Handle | 60-120일 | 0.85 | 컵 깊이 15-40%, 손잡이 15% 이내 |
| Double Bottom | 40-80일 | 0.80 | W 형태, 바닥 간 5% 이내 |
| Head & Shoulders | 60-100일 | 0.75 | 어깨 높이 차이 10% 이내 |
| Support/Resistance Test | 최근 20일 | 0.70 | ±2% 레벨 3회 이상 테스트 |

**가격 레벨 분석 (Phase 2):**

| 소스 | 포함 레벨 | 우선순위 |
|------|----------|---------|
| MA | 20/50/200일 | 3 (높음) |
| Swing | High/Low | 3 (높음) |
| Pivot | S1/R1 | 2 (중간) |
| Fibonacci | 9개 (0.236~2.0) | 1 (낮음) |
| ATR | 1x/2x 지지/저항 | 0 (최하) |
| Pattern | 돌파 레벨 + 목표가 | 패턴 신뢰도 기반 |

- 중복 제거: 현재가 ±5% 내 0.5% threshold, 그 외 1.0%
- 정렬: 지지선 높은 순, 저항선 낮은 순 (가까운 것 우선)
- 출력: 각각 상위 5개 + 패턴 타겟

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

**의존성:** yfinance, LLM (OpenAI/Anthropic), scipy (peak detection), SEC EDGAR, OpenDART (선택), KIS API (선택)

---

## 3. Portfolio Monitoring (`jarvis portfolio`)

KIS 계좌의 보유 종목별 기술적 분석 + 최근 뉴스.

**입출력:**
- 입력: 없음 (KIS 인증 정보 사용)
- 출력: 총자산, 현금, 보유 종목별 P&L + 기술적 평가 + 뉴스 3건

**의존성:** KIS API (잔고 조회), yfinance (기술 분석), NewsTool

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

**의존성:** Naver API, yfinance, KIS API (선택)

---

## 5. Daily Report Pipeline (`jarvis report daily`)

텔레그램 채널 메시지를 5단계 MapReduce로 분석하여 일일 시장 리포트 생성.

**5단계 파이프라인:**

| Stage | 역할 | LLM | 입력 → 출력 |
|-------|------|-----|------------|
| **Ingest** | 메시지 + 매크로 로드 | X | CSV → IngestResult |
| **Map** | 이슈 추출, 카테고리 분류 | Haiku 4.5 (temp 0.2) | messages → MappedIssue[] |
| **Shuffle** | 카테고리 그룹핑 + 테마 정규화 | Haiku 4.5 (temp 0.1) | issues → ShuffleResult |
| **Reduce** | 테마별 분석 리포트 | Haiku 4.5 (temp 0.3) | theme groups → NewsItem[] |
| **Wrapup** | 크로스 테마 인사이트 | Haiku 4.5 (temp 0.4) | news items → DailyReport |

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

**설정 (`config.py`):**

| 설정 | 값 | 용도 |
|------|---|------|
| `MAP_LLM` | Anthropic Haiku 4.5, temp 0.2 | Map 스테이지 |
| `SHUFFLE_LLM` | Anthropic Haiku 4.5, temp 0.1 | Shuffle 스테이지 |
| `REDUCE_LLM` | Anthropic Haiku 4.5, temp 0.3 | Reduce 스테이지 |
| `WRAPUP_LLM` | Anthropic Haiku 4.5, temp 0.4 | Wrapup 스테이지 |
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
- Anthropic provider일 때 system prompt에 `cache_control: ephemeral` 자동 적용
- OpenAI로 전환 시 자동 비활성화 (`StageLLMConfig.build_messages()`)

**리포트 출력:**
- Markdown 파일: `reports/YYYY-MM/daily_YYYY-MM-DD.md`
- 각 테마마다 **출처** 섹션에 원본 메시지 발췌 포함
- source_ids로 CSV에서 원본 메시지 로드 → keywords 매칭 시 주변 ~200자 발췌, 매칭 없으면 전체 메시지
- **포맷**: 개행문자 변환, 출처에 채널명+인용블록, 테마 구분선(`---`)

**의존성:** 텔레그램 CSV, Anthropic Haiku 4.5, yfinance, fear-and-greed

---

## 6. Ticker Report (`jarvis report ticker`)

지정 티커의 매크로 + 기술적 분석 스냅샷.

**입출력:**
- 입력: 티커 목록 (기본: AAPL,MSFT,NVDA)
- 출력: 매크로 (VIX, F&G, 금리, DXY, WTI) + 종목별 기술 점수

**의존성:** yfinance, MacroTool

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

## 8. Ticker Resolution

종목명/티커 자동 변환 시스템. 모든 파이프라인에서 공통 사용.

**변환 우선순위:**
1. 정규식 직접 매칭 (AAPL, 005930.KS 등)
2. 로컬 캐시 조회 (6개월 TTL)
3. LLM Agent (GPT-4o + DuckDuckGo 검색)

**캐시:** `~/.cache/invest-jarvis/user_mappings.yaml`

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
