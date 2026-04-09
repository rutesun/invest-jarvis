# Screener (종목 발굴) Design

**생성일**: 2026-04-09
**버전**: 1.0
**상태**: 승인됨

---

## 1. 개요

시장의 주도주와 주도 테마를 자동 발굴하고, 상위 종목의 뉴스를 수집하는 Screener 기능.

### 1.1 목표
- 오늘 시장의 주도주 검색 (상승률, 거래량, 수급 정보 활용)
- 오늘 시장의 주도 테마 검색
- 상위 종목들의 뉴스 검색
- 결과를 CLI 출력 + 마크다운 파일 저장

### 1.2 시장 범위
- 한국: Naver API + KIS API
- 미국: KIS 해외 API + YFinance

### 1.3 CLI
```bash
jarvis screen              # 한국+미국 모두
jarvis screen --market=kr  # 한국만
jarvis screen --market=us  # 미국만
```

---

## 2. 아키텍처

```
jarvis screen [--market=kr|us|all]
       │
       ▼
  ScreenerPipeline
       │
       ├─ 1. Universe 구축 (종목 수집)
       │     ├─ KR: NaverProvider (테마, 거래량, 상승률 랭킹)
       │     │   + KISProvider (외국인/기관 순매수 랭킹)
       │     └─ US: KISProvider (해외 상승률/거래량 랭킹)
       │
       ├─ 2. Evidence 수집 + 스코어링 (병렬, concurrency=10)
       │     ├─ Accumulation (수급)
       │     ├─ Up Days (상승일수)
       │     ├─ Volume Burst (거래량 급증)
       │     ├─ Source Diversity (복수 소스 보너스)
       │     └─ Momentum Signals (돌파/전환/압축)
       │
       ├─ 3. 테마 집계 + 랭킹
       │
       └─ 4. 상위 종목 뉴스 수집 (NewsTool)
```

---

## 3. 파일 구조

```
src/
├── providers/
│   └── naver.py                 # NaverProvider (테마, 랭킹)
├── tools/
│   └── screener/
│       ├── __init__.py
│       ├── universe.py          # Universe 구축 (KR/US)
│       ├── scoring.py           # 5팩터 스코어링
│       └── evidence.py          # Evidence 수집 + 조합
├── pipelines/
│   └── screener.py              # ScreenerPipeline
└── cli/
    └── main.py                  # screen 명령어 추가

reports/
└── 2026-04/
    └── screen-2026-04-09.md     # 일별 파일, 월별 디렉토리
```

---

## 4. NaverProvider

**위치:** `src/providers/naver.py`

### 4.1 테마 리스트 + 테마별 종목 (JSON API)

```
GET https://stock.naver.com/api/domestic/market/theme/list
  ?startIdx=0&pageSize=200&sortType=changeRate

GET https://stock.naver.com/api/domestic/market/theme/{themeId}/stocklist
  ?startIdx=0&pageSize=200&marketType=
```

**메서드:**
```python
async def get_themes(self, top_n: int = 10) -> list[dict]:
    """상승률 상위 N개 테마 + 소속 종목 반환."""
    # Returns: [{name, change_rate, theme_id, stocks: [{code, name, market}]}]

async def get_theme_stocks(self, theme_id: str) -> list[dict]:
    """특정 테마의 종목 리스트."""
    # Returns: [{code, name, market}]
```

### 4.2 거래량 랭킹 (HTML 파싱)

```
GET https://finance.naver.com/sise/sise_quant.naver?sosok=0  # KOSPI
GET https://finance.naver.com/sise/sise_quant.naver?sosok=1  # KOSDAQ
```

**메서드:**
```python
async def get_volume_ranking(self, top_n: int = 30) -> list[dict]:
    """KOSPI+KOSDAQ 거래량 상위 종목."""
    # Returns: [{code, name, market, price, change_pct, volume}]
```

### 4.3 상승률 랭킹 (HTML 파싱)

```
GET https://finance.naver.com/sise/sise_rise.naver?sosok=0   # KOSPI
GET https://finance.naver.com/sise/sise_rise.naver?sosok=1   # KOSDAQ
```

**메서드:**
```python
async def get_rise_ranking(self, top_n: int = 30) -> list[dict]:
    """KOSPI+KOSDAQ 상승률 상위 종목."""
    # Returns: [{code, name, market, price, change_pct, volume}]
```

### 4.4 HTML 파싱

telegram의 `flow.py` 정규식 로직 참고. httpx 비동기 요청. 재시도 3회.

---

## 5. Universe 구축

**위치:** `src/tools/screener/universe.py`

### 5.1 KR Universe (4개 소스)

| 소스 | Provider | 수집 대상 | 기본값 |
|------|----------|-----------|--------|
| 테마 상위 | NaverProvider | 상승률 상위 N개 테마의 종목 | top 10 테마 |
| 거래량 상위 | NaverProvider | KOSPI+KOSDAQ 거래량 상위 | 시장별 top 30 |
| 상승률 상위 | NaverProvider | KOSPI+KOSDAQ 상승률 상위 | 시장별 top 30 |
| 외국인/기관 순매수 | KISProvider | 순매수 상위 종목 | top 30 |

### 5.2 US Universe (2개 소스)

| 소스 | Provider | 수집 대상 | 기본값 |
|------|----------|-----------|--------|
| 상승률 상위 | KISProvider | NAS+NYS 상승률 | top 30 |
| 거래량 상위 | KISProvider | NAS+NYS 거래량 | top 30 |

### 5.3 KISProvider 확장 필요

기존 KISProvider에 추가할 메서드:

```python
# 한국: 외국인/기관 순매수 랭킹
async def get_investor_ranking(self, investor_type: str = "foreign", top_n: int = 30) -> list[dict]:
    """외국인/기관 순매수 상위 종목."""
    # TR: FHPTJ04400000
    # investor_type: "foreign" (FID_ETC_CLS_CODE=1) or "institution" (=2)

# 미국: 상승률 랭킹
async def get_us_ranking_updown(self, exchange: str = "NAS", direction: str = "up", top_n: int = 30) -> list[dict]:
    """미국 상승/하락률 랭킹."""
    # TR: HHDFS76290000, GUBN: 1=up, 0=down

# 미국: 거래량 랭킹
async def get_us_ranking_volume(self, exchange: str = "NAS", top_n: int = 30) -> list[dict]:
    """미국 거래량 랭킹."""
    # TR: HHDFS76320010
```

### 5.4 데이터 모델

```python
class UniverseStock(BaseModel):
    ticker: str
    name: str
    market: str               # "KOSPI", "KOSDAQ", "NAS", "NYS"
    sources: list[str]        # ["theme", "volume_rank", "rise_rank", "kis_rank"]
    theme: str | None = None
    theme_change_rate: float | None = None
    price: float | None = None
    change_pct: float | None = None
```

종목 코드 기준으로 중복 제거. sources 리스트에 어디서 발견됐는지 누적.

---

## 6. 스코어링 시스템

**위치:** `src/tools/screener/scoring.py`

### 6.1 4개 스코어링 팩터 + 1개 수집 전용

**1. Accumulation Score (수급) — 0~15**
- KIS 투자자 동향 API로 최근 10일 외국인+기관 순매수 조회
- positive_days = 순매수 > 0인 날 수
- net_sum > 0이면 score = positive_days × 1.5, 아니면 0
- US 종목은 이 팩터 스킵 (데이터 없음)

**2. Up Days (상승일수) — 수집만, 스코어링 불포함**
- OHLCV에서 Close > Open인 날 수 (최근 10일)
- ScreenerEvidence에 필드로 기록하되, total_score에 합산하지 않음
- 참고 지표로만 활용

**3. Volume Burst Score (거래량 급증) — 0~8**
- vol_ratio = 당일 거래량 / 20일 평균 거래량
- score = clamp(vol_ratio - 1.5, 0, 8.0)
- ratio < 1.5이면 0점

**4. Source Diversity Bonus (소스 다양성) — 0~10**
- 가중치: theme=1.0, volume_rank=1.5, rise_rank=1.0, kis_rank=1.5
- weighted_sum = sum(해당 소스 가중치)
- bonus = min(10, 2.0 × (weighted_sum - 1.0))

**5. Momentum Signals (모멘텀) — 0~112**
- Breakout: 종가 > 전 N일 최고가 → +12
- Trend Reversal: SuperTrend -1 → +1 전환 → +25
- Compression: 최근 10일 ATR < 이전 10일 ATR → +15
- Flow: accumulation_score × 5.0
- Combo: breakout + reversal 동시 → +10

### 6.2 랭킹

```python
sort_key = (
    momentum_total DESC,       # Primary
    total_score DESC,
    source_diversity_bonus DESC,
)
```

### 6.3 결과 모델

```python
class ScreenerEvidence(BaseModel):
    stock: UniverseStock
    accumulation_score: float
    up_days_score: float
    volume_burst_score: float
    source_diversity_bonus: float
    momentum_total: float
    total_score: float
    vol_ratio: float
    rank: int
```

---

## 7. Evidence 수집

**위치:** `src/tools/screener/evidence.py`

### 7.1 수집 흐름

```python
async def collect_and_score(self, universe: list[UniverseStock]) -> list[ScreenerEvidence]:
    """Universe 전체에 대해 evidence 수집 + 스코어링."""
    # 병렬 처리 (asyncio.Semaphore, concurrency=10)
    tasks = [self._collect_one(stock) for stock in universe]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 에러 제외, 랭킹
    scored = [r for r in results if isinstance(r, ScreenerEvidence)]
    scored.sort(key=lambda x: (x.momentum_total, x.total_score), reverse=True)
    for i, item in enumerate(scored):
        item.rank = i + 1

    return scored
```

### 7.2 티커 직접 스코어링 (재사용 인터페이스)

Universe 구축 없이 티커만으로 스코어링. 다른 파이프라인에서 재사용 가능.

```python
async def score_tickers(self, tickers: list[str]) -> list[ScreenerEvidence]:
    """티커 리스트로 직접 스코어링. Universe 구축 없이 동작."""
    universe = [
        UniverseStock(
            ticker=ticker,
            name=ticker,
            market=self._detect_market(ticker),
            sources=["direct"],
        )
        for ticker in tickers
    ]
    return await self.collect_and_score(universe)

def _detect_market(self, ticker: str) -> str:
    """티커 형식으로 시장 추정."""
    if ticker.endswith(".KS"):
        return "KOSPI"
    elif ticker.endswith(".KQ"):
        return "KOSDAQ"
    elif ticker.isdigit() and len(ticker) == 6:
        return "KOSPI"
    return "US"
```

**활용처:**
- `jarvis check AAPL` → 기술적 분석 + 모멘텀 스코어 함께 표시
- 포트폴리오 모니터링 → 보유 종목별 모멘텀 스코어
- 워치리스트 → 관심 종목 비교 스코어링
- Daily Report → 종목별 모멘텀 스코어 추가

### 7.3 단일 종목 수집

```python
async def _collect_one(self, stock: UniverseStock) -> ScreenerEvidence:
    # 1. OHLCV 조회 (140일, KIS or YFinance)
    # 2. 투자자 동향 조회 (KR만, KIS)
    # 3. 지표 계산 (SMA, ATR, SuperTrend via IndicatorCalculator)
    # 4. 5팩터 스코어링
    # 5. ScreenerEvidence 반환
```

---

## 8. ScreenerPipeline

**위치:** `src/pipelines/screener.py`

### 8.1 실행

```python
class ScreenerPipeline:
    def __init__(
        self,
        naver_provider: NaverProvider,
        kis_provider: KISProvider | None,
        yf_provider: YFinanceProvider,
        news_tool: NewsTool,
    ):
        self.universe_builder = UniverseBuilder(naver_provider, kis_provider, yf_provider)
        self.evidence_collector = EvidenceCollector(kis_provider, yf_provider)
        self.news_tool = news_tool

    async def run(self, market: str = "all") -> dict:
        # 1. Universe 구축
        universe = await self.universe_builder.build(market)

        # 2. Evidence 수집 + 스코어링
        scored = await self.evidence_collector.collect_and_score(universe)

        # 3. 테마 집계
        theme_ranking = self._aggregate_themes(scored)

        # 4. 상위 종목 뉴스 (top 10)
        top_stocks = scored[:10]
        news = await self._fetch_news_for_top(top_stocks)

        return {
            "market": market,
            "timestamp": datetime.now(),
            "leaders": scored[:20],
            "themes": theme_ranking[:10],
            "news": news,
            "total_universe_size": len(universe),
        }
```

### 8.2 테마 집계

```python
def _aggregate_themes(self, scored: list[ScreenerEvidence]) -> list[dict]:
    """scored 종목들의 테마를 그룹핑하여 랭킹."""
    themes = {}
    for item in scored:
        theme = item.stock.theme
        if not theme:
            continue
        if theme not in themes:
            themes[theme] = {
                "name": theme,
                "change_rate": item.stock.theme_change_rate,
                "stock_count": 0,
                "top_stocks": [],
                "momentum_sum": 0.0,
            }
        themes[theme]["stock_count"] += 1
        themes[theme]["momentum_sum"] += item.momentum_total
        if len(themes[theme]["top_stocks"]) < 3:
            themes[theme]["top_stocks"].append(item.stock.name)

    # avg_momentum으로 정렬
    result = list(themes.values())
    for t in result:
        t["avg_momentum"] = t["momentum_sum"] / t["stock_count"] if t["stock_count"] > 0 else 0
    result.sort(key=lambda x: x["avg_momentum"], reverse=True)
    return result
```

---

## 9. CLI

### 9.1 명령어

```python
@app.command()
def screen(
    market: str = typer.Option("all", "--market", "-m", help="kr, us, or all"),
):
    """Scan market for leading stocks and themes."""
```

### 9.2 출력 포맷

```markdown
# Market Screener (2026-04-09)

## 주도 테마 TOP 10
| # | 테마 | 등락률 | 종목수 | 주요 종목 |
|---|------|--------|--------|-----------|
| 1 | AI/반도체 | +3.2% | 8 | 삼성전자, SK하이닉스, ... |
| 2 | 2차전지 | +2.1% | 5 | LG에너지솔루션, ... |

## 주도주 TOP 20
| # | 종목 | 시장 | 등락률 | 모멘텀 | 수급 | 소스 |
|---|------|------|--------|--------|------|------|
| 1 | SK하이닉스 | KOSPI | +5.2% | 47.0 | 8/10 | 테마,거래량,기관 |
| 2 | NVDA | NAS | +4.1% | 42.0 | - | 상승률,거래량 |

## 상위 종목 뉴스
### SK하이닉스
- HBM 수주 확대 소식 (2026-04-09)
- 반도체 업황 개선 전망 (2026-04-09)

### NVDA
- AI 칩 수요 증가 (2026-04-09)
```

---

## 10. 파일 저장

### 10.1 경로

```
reports/{yyyy-MM}/screen-{yyyy-MM-dd}.md
```

예시:
```
reports/2026-04/screen-2026-04-09.md
```

### 10.2 저장 로직

```python
def save_report(self, result: dict) -> Path:
    timestamp = result["timestamp"]
    dir_path = Path("reports") / timestamp.strftime("%Y-%m")
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"screen-{timestamp.strftime('%Y-%m-%d')}.md"
    file_path.write_text(self.format_output(result))
    return file_path
```

CLI에서 자동 저장 후 경로 출력:
```
Report saved to reports/2026-04/screen-2026-04-09.md
```

---

## 11. 영향 범위

### 11.1 신규 파일

| 파일 | 내용 |
|------|------|
| `src/providers/naver.py` | NaverProvider (테마, 랭킹) |
| `src/tools/screener/__init__.py` | screener 패키지 |
| `src/tools/screener/universe.py` | Universe 구축 |
| `src/tools/screener/scoring.py` | 5팩터 스코어링 |
| `src/tools/screener/evidence.py` | Evidence 수집 |
| `src/pipelines/screener.py` | ScreenerPipeline |

### 11.2 수정 파일

| 파일 | 변경 |
|------|------|
| `src/providers/kis.py` | 투자자 랭킹, 미국 랭킹 메서드 추가 |
| `src/cli/main.py` | screen 명령어 추가 |

### 11.3 변경 없음

기존 tools, pipelines, strategies 모두 변경 없음.

---

## 12. 의존성

**추가 필요 없음.** httpx (이미 있음), yfinance (이미 있음).

HTML 파싱은 정규식 기반 (추가 라이브러리 불필요, telegram 방식과 동일).
