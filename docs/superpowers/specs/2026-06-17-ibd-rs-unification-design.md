# IBD RS 통일 설계 스펙

- **작성일**: 2026-06-17
- **상태**: Draft v1
- **대상**: `criteria` 엔진의 상대강도(RS) — 종목 RS·업종 강세 판정을 IBD 가중 공식으로 통일하고, 데이터 소스를 시장별로 단일화한다.
- **구현 플랜**: 작성 예정 (`docs/superpowers/plans/2026-06-17-ibd-rs-unification.md`)
- **출처 자료**: [skyte/relative-strength](https://github.com/skyte/relative-strength) — IBD Style RS percentile ranking. 본 설계는 그 가중 강도 공식(`strength`, `relative_strength`)을 차용하되, 단일 종목 도구 특성상 유니버스 percentile(1~99) 대신 **지수 대비 비율(100 기준)** 을 쓴다.

---

## 1. 배경 및 목표

### 1.1 문제 1 — 시간축 불일치 (종목 RS vs 업종 강세)

현재 두 지표가 서로 다른 시간축으로 강세를 판정한다.

| 지표 | 현재 판정 기준 | 시간축 |
|------|----------------|--------|
| 종목 RS (`RelativeStrengthResult.is_strong`) | `mansfield_rs > 0 and rp_slope_4w >= 0` (52주 상대가격선 + 4주 기울기) | 다기간 |
| 업종 강세 (`SectorStrengthResult.is_strong`) | `rank_pct <= 0.5 and trend == "up"` (**하루 등락률 순위** + 60일 추세) | 하루 rank가 게이트 |

실증: 2026-06-16 FMP `industry-performance-snapshot`에서 "Electrical Equipment & Parts"는 당일 등락 `-4.96%`로 전체 업종 중 하위 2위. 종목(BE)의 60일 추세가 좋아도 **하루 급락 한 번에 `업종강세=False`** 로 떨어졌다. 종목 RS는 52주를 보는데 업종은 하루를 본다.

### 1.2 문제 2 — RS 데이터 소스 혼합 (한국)

한국 종목의 종목 RS는 **분자와 분모의 소스가 다르다**.

| RS 데이터 | 현재 소스 | bars(실측) |
|-----------|-----------|------------|
| 한국 종목 close (분자) | KIS `inquire-daily-itemchartprice` (페이징 구현됨) | 272 (1y) |
| 한국 RS 벤치마크 코스피 (분모) | yfinance `^KS11` | 486 (2y) |

종목 기술분석은 KIS로 받으면서 RS 벤치마크만 yfinance를 쓰는 일관성 결함이다. 한 종목의 상대강도를 KIS 종가 ÷ yfinance 종가로 계산하고 있다.

### 1.3 FMP의 한계 — 업종 IBD 불가

미국 업종을 IBD 다기간으로 계산하려면 업종의 가격(또는 수익률) 시계열 252거래일이 필요하다. 그러나 FMP `historical-industry-performance`는 **21거래일치(약 1개월)만, 그것도 2024-03에서 멈춘 낡은 데이터**를 반환한다(무료 티어). FMP로는 업종 IBD가 불가능하다.

### 1.4 목표

1. **하나의 공식**: 종목·업종·미국·한국 모두 동일한 IBD 가중 강도 공식으로 RS를 계산하고 `is_strong`을 `ibd_rs > 100`으로 통일한다.
2. **시장별 단일 소스**: 미국 = 전부 yfinance, 한국 = 전부 KIS. RS 계산에서 소스 혼합을 없앤다.
3. **추상화**: RS 시계열 공급을 시장 독립적인 인터페이스 뒤로 숨겨, 새 시장은 provider만 추가하면 되게 한다.

---

## 2. 설계 결정 요약

| 항목 | 결정 | 근거 |
|------|------|------|
| RS 공식 | IBD 가중 강도 (0.4/0.2/0.2/0.2), 지수 대비 비율 100 기준 | 종목·업종 같은 기준 (사용자 결정) |
| `is_strong` 판정 | `ibd_rs > 100` (종목·업종 공통) | 시장 대비 강세 단일 정의 |
| 종목 RS 기존 지표 | Mansfield·outperform·slope·rs_cross **유지** (보조·이벤트용) | 출력 맥락·RS 전환 이벤트 보존 |
| 미국 업종 소스 | 대표 ETF close (yfinance) | FMP 21일 한계 회피, 종목과 동일 소스 |
| 미국 업종 단위 | 세부 업종 ETF 우선 + 섹터 ETF fallback | 커버리지 조사 결과 (§7) |
| 한국 RS 소스 | 전부 KIS (종목·업종지수·코스피) | 소스 혼합 제거 |
| 한국 업종지수 페이징 | `get_sector_index_history`에 종목 일봉과 동일 페이징 추가 | 50→252 bars |
| FMP | **완전 제거** (`FmpProvider`·`FmpSectorStrength`·`YF_TO_FMP_INDUSTRY`) | 낡은/짧은 데이터, ETF가 대체 |
| `rank_pct` | 제거 → `ibd_rs`로 대체 | 하루 등락률 순위 폐기 |
| 추상화 | `RsSeriesProvider` (US: yfinance / KR: KIS) | 시장 독립 판정 (사용자 요청) |
| market_regime 소스 통일 | **비범위** (후속) | RS 내부 통일에 집중 |

---

## 3. IBD 가중 공식 (공통 코어)

skyte/relative-strength의 공식을 그대로 차용한다.

```text
quarter_perf(closes, n) = 최근 (n × 63)거래일의 누적수익률
    63 ≈ 252/4 (1분기)

ibd_strength(closes) = 0.4·quarter_perf(closes,1)
                     + 0.2·quarter_perf(closes,2)
                     + 0.2·quarter_perf(closes,3)
                     + 0.2·quarter_perf(closes,4)
    → 최근 1분기를 2배 가중한 12개월 모멘텀

ibd_relative_strength(target, benchmark)
    = (1 + ibd_strength(target)) / (1 + ibd_strength(benchmark)) × 100
    → 100 초과 = 시장(벤치마크)보다 강함
```

- 입력은 종가 시리즈(`pd.Series`)만. 네트워크 호출 없는 **순수 함수**.
- 데이터가 252거래일 미만이면 가능한 분기까지만 계산(짧으면 분기 수 축소). 최소 1분기(63일) 미만이면 `None`.
- `is_strong = ibd_rs > 100`.

배치 위치: `src/tools/criteria/ibd_rs.py` (신규).

---

## 4. 아키텍처 — 추상화

```text
[순수 코어]   src/tools/criteria/ibd_rs.py
    ibd_strength(closes) -> float | None
    ibd_relative_strength(target, benchmark) -> float | None
        ↑ 시장·자산 무관. 종목·업종·미국·한국 전부 이 함수로 판정.

[추상 인터페이스]  src/tools/criteria/rs_source.py  (신규)
    class RsSeriesProvider(ABC):
        async def stock_series(ticker)            -> RsPair | None
        async def sector_series(ticker, industry, sector) -> SectorRsPair | None
            RsPair       = (target_closes, benchmark_closes, benchmark_symbol)
            SectorRsPair = RsPair + proxy_symbol (ETF 티커 또는 KIS 업종코드)

    ├─ UsRsProvider(yfinance)
    │     stock:  종목 close + ^GSPC
    │     sector: industry→ETF(세부 우선, 섹터 fallback) + SPY
    └─ KrRsProvider(KIS)
          stock:  종목 일봉(KIS, 페이징) + 코스피 0001(KIS, 페이징)
          sector: 업종지수(KIS, 페이징) + 코스피 0001(KIS, 페이징)

[판정]  compute_relative_strength / compute_sector_strength
    pair = await provider.stock_series(ticker)
    ibd_rs = ibd_relative_strength(pair.target, pair.benchmark)
    is_strong = ibd_rs > 100
```

`CriteriaEngine`은 시장에 맞는 `RsSeriesProvider`를 주입받는다(미국→`UsRsProvider`, 한국→`KrRsProvider`). 판정 로직(`ibd_relative_strength`)은 provider와 무관하게 단일하다.

---

## 5. 데이터 흐름

### 5.1 미국 (yfinance)

```text
종목 RS:  yf(ticker).Close ──┐
          yf(^GSPC).Close ──┴→ ibd_relative_strength → ibd_rs, is_strong
업종 RS:  industry → ETF 결정 → yf(ETF).Close ──┐
          yf(SPY).Close ─────────────────────────┴→ ibd_relative_strength
```

### 5.2 한국 (KIS)

```text
종목 RS:  KIS itemchartprice(code) ─┐  (페이징 구현됨, 272 bars)
          KIS indexchartprice(0001) ┴→ ibd_relative_strength   (코스피, 페이징 추가)
업종 RS:  KIS indexchartprice(sector_code) ─┐  (페이징 추가)
          KIS indexchartprice(0001) ─────────┴→ ibd_relative_strength
```

코스피(0001) 시계열은 종목 RS·업종 RS가 공유하므로 분석당 1회만 fetch한다(`KrRsProvider` 인스턴스 캐시).

---

## 6. 모델 변경

### 6.1 `RelativeStrengthResult`
- **추가**: `ibd_rs: float`
- **변경**: `is_strong`(computed) → `ibd_rs > 100`
- **유지**: `mansfield_rs`, `outperform_6m`, `rp_slope_4w`, `rs_cross_*` (출력·Event 섹션 보조 지표). `rs_cross`(양/음전환)는 Mansfield 시리즈 기반으로 계속 감지.

### 6.2 `SectorStrengthResult`
- **추가**: `ibd_rs: float`, `proxy_symbol: str`(ETF 티커 또는 KIS 업종코드)
- **변경**: `is_strong` → `ibd_rs > 100`
- **제거**: `rank_pct`, `trend` (하루 등락률 순위·별도 추세 판정 폐기 — IBD가 추세를 내포)
- **유지**: `industry`, `source`("ETF"|"KIS")

---

## 7. 미국 업종 ETF 매핑

### 7.1 커버리지 조사 결과

yfinance 분류 기준 11개 섹터·145개 세부 업종. 세부 업종 ETF 31종 전부 yfinance 1년 데이터 정상. 섹터 내 비중 기준 세부 ETF 커버리지:

| 섹터 | 세부 ETF 커버 |
|------|:---:|
| Healthcare | 84.0% |
| Consumer Cyclical | 70.7% |
| Technology | 69.6% |
| Financial | 67.6% |
| Energy | 52.1% |
| Industrials | 51.4% |
| Basic Materials | 51.4% |
| Communication | 22.6% |
| Consumer Defensive / Real Estate / Utilities | 0% |

성장·모멘텀이 몰리는 섹터(Tech·Healthcare·Consumer Cyclical·Financial)는 세부 ETF가 67~84% 커버한다. 세부 ETF가 없는 방어 섹터(Defensive·Utilities·Real Estate)는 섹터 단위로 움직이므로 섹터 ETF fallback이 적절하다.

### 7.2 매핑 규칙

종목의 yfinance `industry`(정규화된 키) → 세부 ETF 있으면 사용, 없으면 `sector` → SPDR 섹터 ETF. **모든 종목이 세부 또는 섹터 ETF로 항상 매핑**된다.

세부 업종 ETF (industry-key → ETF):

```python
INDUSTRY_ETF = {
    # Technology
    "semiconductors": "SOXX", "semiconductor-equipment-materials": "SOXX",
    "software-infrastructure": "IGV", "software-application": "IGV", "solar": "TAN",
    # Financial
    "banks-diversified": "KBWB", "banks-regional": "KRE", "capital-markets": "IAI",
    "insurance-diversified": "KIE", "insurance-property-casualty": "KIE",
    "insurance-life": "KIE", "insurance-brokers": "KIE",
    "insurance-specialty": "KIE", "insurance-reinsurance": "KIE",
    # Healthcare
    "drug-manufacturers-general": "IHE", "drug-manufacturers-specialty-generic": "IHE",
    "biotechnology": "XBI", "healthcare-plans": "IHF",
    "medical-devices": "IHI", "medical-instruments-supplies": "IHI",
    # Consumer Cyclical
    "internet-retail": "ONLN", "auto-manufacturers": "CARZ",
    "residential-construction": "ITB", "home-improvement-retail": "XHB",
    "apparel-retail": "XRT", "specialty-retail": "XRT", "department-stores": "XRT",
    # Energy
    "oil-gas-midstream": "AMLP", "oil-gas-e-p": "XOP",
    "oil-gas-equipment-services": "OIH", "oil-gas-drilling": "OIH", "uranium": "URA",
    # Industrials
    "aerospace-defense": "ITA", "airlines": "JETS",
    "railroads": "IYT", "trucking": "IYT", "integrated-freight-logistics": "IYT",
    # Basic Materials
    "gold": "GDX", "copper": "COPX", "steel": "SLX", "silver": "SIL",
    "other-industrial-metals-mining": "XME", "other-precious-metals-mining": "GDX",
    # Communication Services
    "electronic-gaming-multimedia": "ESPO", "telecom-services": "IYZ", "entertainment": "PEJ",
}

SECTOR_ETF = {  # GICS 섹터 → SPDR (fallback)
    "technology": "XLK", "financial-services": "XLF", "healthcare": "XLV",
    "consumer-cyclical": "XLY", "consumer-defensive": "XLP", "energy": "XLE",
    "industrials": "XLI", "basic-materials": "XLB", "real-estate": "XLRE",
    "utilities": "XLU", "communication-services": "XLC",
}
```

yfinance `industry`/`sector` 문자열을 위 키(kebab-case)로 정규화하는 헬퍼가 필요하다(예: `"Electrical Equipment & Parts"` → `"electrical-equipment-parts"` → 세부 ETF 없음 → sector `"industrials"` → `XLI`).

---

## 8. 한국 KIS 페이징

`get_sector_index_history`(tr `FHKUP03500100`, indexchartprice)는 현재 페이징이 없어 종료일 기준 직전 50거래일만 반환한다(실측). 종목 일봉 `get_price_history`(tr `FHKST03010100`, itemchartprice)에 이미 구현된 페이징 패턴(종료일을 100일씩 앞으로 이동하며 누적, 중복 제거)을 동일하게 적용해 252거래일을 확보한다.

실측 근거:
- `0001`(코스피) `period="1y"` 요청 → 50 bars(2026-04-03~06-17)만 반환.
- 과거 구간 명시(`2025-09-01~12-31`) 호출 → `10/21~12/30` 50 bars 반환 → 종료일을 옮기면 과거 누적 가능 확인.

---

## 9. 표시 변경

- canslim L (`_judge_l`): `업종강세=True (Semiconductors→SOXX, RS 112)` 형식. "상위/하위 %" 표기 제거(`rank_pct` 폐기에 동반).
- 종목 RS 출력: `ibd_rs`를 주 수치로, Mansfield 등은 보조로 병기.

---

## 10. 범위 / 비범위

**범위**
- IBD 코어(`ibd_rs.py`), 추상화(`rs_source.py`), `UsRsProvider`/`KrRsProvider`
- 종목 RS·미국 업종·한국 업종 IBD 통일
- `get_sector_index_history` 페이징 추가
- FMP 제거, `rank_pct`/`trend` 제거, 모델 변경, 표시 변경

**비범위(후속)**
- `market_regime`(시장 국면)의 index 소스 통일 — RS provider와 별개로 기존 `IndexProvider`(yfinance) 유지. 한국에서 RS 벤치마크(KIS 코스피)와 market_regime 벤치마크(yfinance ^KS11)가 일시적으로 다른 소스를 쓰게 되나, 모듈이 분리되어 RS 내부 일관성에는 영향 없음.
- 한국 업종 ETF화(KIS 업종지수 대신 ETF) — 한국은 KIS 업종지수가 정식 소스.

---

## 11. 마이그레이션

- 삭제: `src/providers/fmp_provider.py`(`FmpProvider`), `src/tools/criteria/sector_strength.py`의 `FmpSectorStrength`·`YF_TO_FMP_INDUSTRY`·`_rank_pct`·`_trend_from_hist`.
- `CriteriaEngine`: `fmp_provider` 파라미터 제거, `rs_provider`(RsSeriesProvider) 주입으로 교체. `_fetch_sector_strength`/`_fetch_fmp_sector`/`_fetch_kis_sector`를 provider 기반으로 재작성.
- `main.py`: FMP 키 읽기 제거, 시장에 맞는 `RsSeriesProvider` 주입.
- 영향 테스트: `test_sector_strength.py`, `test_canslim.py`(rank_pct/상위·하위 표기), `test_engine.py`, `test_relative_strength.py` 업데이트.

---

## 12. 테스트 전략

- `ibd_rs.py`: 알려진 입력에 대한 `ibd_strength`/`ibd_relative_strength` 단위 테스트. 짧은 시리즈(분기 축소)·빈 시리즈(None) 경계.
- ETF 매핑: industry/sector 정규화 + 세부→fallback 결정 단위 테스트(`"Electrical Equipment & Parts"`→`XLI` 회귀 케이스 포함).
- `RsSeriesProvider`: 가짜 close 시리즈를 반환하는 mock provider로 판정 로직 검증(네트워크 없이).
- `is_strong = ibd_rs > 100` 경계 테스트.
- 한국 페이징: `get_sector_index_history`가 252 bars 이상 누적·중복 제거하는지(mock httpx).

---

## 13. 조사 근거 (재현)

- 미국 ETF 1년 데이터: `yf.Ticker("XLK"/"SOXX"/"XBI").history(period="1y")` → 251 bars, 최신 2026-06-16.
- 세부 ETF 31종 유효성·섹터 커버리지: §7.1 (yfinance `Sector(key).industries` market weight 기준).
- 한국 종목/지수 yfinance: `005930.KS`·`^KS11` 2y → 485~486 bars.
- KIS 종목 일봉 페이징: `KISProvider.get_price_history("005930","1y")` → 272 bars.
- KIS 업종지수 50건 한계 + 과거 구간 페이징 가능: §8.
- FMP 21일·낡은 데이터: `FmpProvider.historical_industry("Semiconductors")` → 21 rows, 2024-02~03.
