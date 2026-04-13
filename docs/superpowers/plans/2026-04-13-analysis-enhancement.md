# Analysis Enhancement (공시 + 수급) 구현 계획

> **에이전트 워커용:** 필수 서브스킬: superpowers:subagent-driven-development (권장) 또는 superpowers:executing-plans 를 사용해 태스크 단위로 구현하세요. 각 스텝은 체크박스(`- [ ]`) 형식으로 진행 상황을 추적합니다.

**목표:** `jarvis analyze`에 SEC EDGAR / DART 공시 조회와 KIS API 수급 데이터(외인/기관 순매수)를 추가하여, 기술적·기본적·공시·수급을 통합한 멀티팩터 종합 추천을 생성한다.

**아키텍처:** 두 개의 신규 툴(`DisclosureTool`, `FlowTool`)을 `DeepDivePipeline`에 주입한다. 파이프라인은 기존 뉴스 호출과 함께 병렬로 이들을 실행하고, 결과 dict에 `disclosure`, `flow`, `integrated_analysis` 키를 추가한다. 새로운 LLM 함수 `generate_integrated_analysis()`가 모든 팩터를 통합해 단일 추천을 생성한다. CLI 포매터는 공시·수급·종합인사이트 3개 섹션을 새로 렌더링한다.

**기술 스택:** Python/asyncio, httpx (기존 의존성), Pydantic v2, LangChain structured output, SEC EDGAR REST API (신규 패키지 불필요), OpenDART REST API (`OPENDART_API_KEY` 환경변수), KIS OpenAPI `get_investor_trend()` (이미 `KISProvider`에 구현됨).

---

## 파일 구조

| 파일 | 작업 | 역할 |
|------|------|------|
| `src/tools/disclosure.py` | **신규 생성** | `DisclosureItem`, 티커 헬퍼, `SECDisclosureFetcher`, `DARTDisclosureFetcher`, `DisclosureTool` |
| `src/tools/flow.py` | **신규 생성** | `InvestorFlowEntry`, `InvestorFlow`, `FlowTool` (KIS `get_investor_trend()` 래퍼) |
| `tests/tools/test_disclosure.py` | **신규 생성** | 공시 관련 클래스 전체 유닛 테스트 |
| `tests/tools/test_flow.py` | **신규 생성** | FlowTool 유닛 테스트 |
| `src/llm/models.py` | **수정** | `IntegratedAnalysisInput`, `IntegratedAnalysisOutput` 추가 |
| `src/llm/analyzer.py` | **수정** | `generate_integrated_analysis()` 추가 |
| `src/pipelines/deep_dive.py` | **수정** | 신규 툴 주입, 병렬 fetch, 결과에 `integrated_analysis` 포함 |
| `tests/pipelines/test_deep_dive.py` | **수정** | 신규 데이터 경로 테스트 추가 |
| `src/cli/main.py` | **수정** | `run_deep_dive()` 에 신규 툴 연결; `format_deep_dive_output()` 에 신규 섹션 렌더링 |
| `README.md` | **수정** | Features + 환경변수 섹션 업데이트 |
| `docs/CLI_USAGE.md` | **수정** | analyze 커맨드 섹션 업데이트 |

---

## Task 1: `DisclosureItem` 모델 + 티커 라우팅 헬퍼

**파일:**
- 신규: `src/tools/disclosure.py`
- 신규: `tests/tools/test_disclosure.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/tools/test_disclosure.py
import pytest
from src.tools.disclosure import DisclosureItem, is_korean_ticker, extract_kr_code


def test_disclosure_item_defaults():
    item = DisclosureItem(
        form_type="8-K",
        date="2026-04-01",
        description="Q1 Results announced",
        url="https://sec.gov/Archives/edgar/data/320193/000032019326000001/q1.htm",
    )
    assert item.form_type == "8-K"
    assert item.score == 1.0  # 기본값


def test_disclosure_item_custom_score():
    item = DisclosureItem(
        form_type="DART",
        date="2026-04-01",
        description="수주계약 체결",
        url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260401000001",
        score=2.0,
    )
    assert item.score == 2.0


def test_is_korean_ticker_ks_suffix():
    assert is_korean_ticker("005930.KS") is True


def test_is_korean_ticker_kq_suffix():
    assert is_korean_ticker("000660.KQ") is True


def test_is_korean_ticker_bare_six_digits():
    assert is_korean_ticker("005930") is True


def test_is_korean_ticker_us_stock():
    assert is_korean_ticker("AAPL") is False
    assert is_korean_ticker("NVDA") is False
    assert is_korean_ticker("MSFT") is False


def test_extract_kr_code_with_ks():
    assert extract_kr_code("005930.KS") == "005930"


def test_extract_kr_code_with_kq():
    assert extract_kr_code("000660.KQ") == "000660"


def test_extract_kr_code_bare():
    assert extract_kr_code("005930") == "005930"


def test_extract_kr_code_pads_short_code():
    # 짧은 코드는 6자리로 0-패딩
    assert extract_kr_code("5930.KS") == "005930"
```

- [ ] **Step 2: 테스트 실패 확인**

```
uv run pytest tests/tools/test_disclosure.py -v
```
예상: `ModuleNotFoundError: No module named 'src.tools.disclosure'`

- [ ] **Step 3: disclosure 모듈 골격 생성**

```python
# src/tools/disclosure.py
"""
공시 데이터 툴: SEC EDGAR (미국주식) 및 DART (한국주식).
"""
import re
from pydantic import BaseModel


class DisclosureItem(BaseModel):
    """공시 1건 (SEC 8-K/10-Q 또는 DART 보고서)."""

    form_type: str    # "8-K", "10-Q", "DART"
    date: str         # "YYYY-MM-DD"
    description: str  # 공시 제목 또는 1차 문서명
    url: str          # 원문 링크
    score: float = 1.0  # 관련도 점수 (DART 키워드 스코어링)


def is_korean_ticker(ticker: str) -> bool:
    """한국주식 여부 판별 (.KS/.KQ 접미사 또는 6자리 숫자)."""
    if re.search(r"\.(KS|KQ)$", ticker, re.IGNORECASE):
        return True
    return bool(re.match(r"^\d{6}$", ticker))


def extract_kr_code(ticker: str) -> str:
    """한국 티커 문자열에서 6자리 KRX 종목코드 추출."""
    cleaned = re.sub(r"\.(KS|KQ)$", "", ticker, flags=re.IGNORECASE)
    return cleaned.zfill(6)
```

- [ ] **Step 4: 테스트 통과 확인**

```
uv run pytest tests/tools/test_disclosure.py -v
```
예상: 10개 통과

- [ ] **Step 5: 커밋**

```bash
git add src/tools/disclosure.py tests/tools/test_disclosure.py
git commit -m "feat: add DisclosureItem model and Korean ticker helpers"
```

---

## Task 2: SEC EDGAR 페처 (CIK 조회 + 공시 수집)

**파일:**
- 수정: `src/tools/disclosure.py`
- 수정: `tests/tools/test_disclosure.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/tools/test_disclosure.py`에 추가:

```python
import json
import time
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.disclosure import SECDisclosureFetcher, DisclosureItem


@pytest.fixture
def sec_fetcher(tmp_path):
    fetcher = SECDisclosureFetcher()
    fetcher.CACHE_PATH = tmp_path / "sec_cik_cache.json"
    return fetcher


@pytest.fixture
def sec_cik_response():
    return {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
    }


@pytest.fixture
def sec_submissions_response():
    return {
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q", "8-K", "DEF 14A"],
                "filingDate": ["2026-04-05", "2026-03-30", "2025-12-01", "2026-03-01"],
                "primaryDocument": ["q1.htm", "10q.htm", "old.htm", "proxy.htm"],
                "accessionNumber": [
                    "0000320193-26-000001",
                    "0000320193-26-000002",
                    "0000320193-25-000099",
                    "0000320193-26-000003",
                ],
            }
        }
    }


@pytest.mark.asyncio
async def test_sec_fetcher_returns_filtered_filings(
    sec_fetcher, sec_cik_response, sec_submissions_response
):
    """최근 3개월 이내의 10-Q, 8-K만 반환하고 오래된 공시와 다른 유형은 제외."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        cik_resp = AsyncMock()
        cik_resp.json.return_value = sec_cik_response
        cik_resp.raise_for_status = MagicMock()

        sub_resp = AsyncMock()
        sub_resp.json.return_value = sec_submissions_response
        sub_resp.raise_for_status = MagicMock()

        mock_client.get.side_effect = [cik_resp, sub_resp]

        items = await sec_fetcher.fetch("AAPL")

    # DEF 14A 제외; 2025-12-01의 8-K는 3개월 범위 밖
    assert len(items) == 2
    assert all(i.form_type in ("8-K", "10-Q") for i in items)
    # 최신순 정렬
    assert items[0].date == "2026-04-05"
    assert items[1].date == "2026-03-30"


@pytest.mark.asyncio
async def test_sec_fetcher_unknown_ticker_returns_empty(sec_fetcher, sec_cik_response):
    """SEC DB에 없는 티커는 빈 리스트 반환."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        cik_resp = AsyncMock()
        cik_resp.json.return_value = sec_cik_response
        cik_resp.raise_for_status = MagicMock()

        mock_client.get.return_value = cik_resp

        items = await sec_fetcher.fetch("UNKNOWN_XYZ")

    assert items == []


@pytest.mark.asyncio
async def test_sec_fetcher_uses_cache(sec_fetcher, sec_submissions_response, tmp_path):
    """두 번째 호출 시 파일 캐시를 사용해 CIK 재조회 없이 처리."""
    # AAPL -> 320193 캐시 사전 저장
    cache_data = {"AAPL": 320193}
    sec_fetcher.CACHE_PATH.write_text(json.dumps(cache_data))
    sec_fetcher.CACHE_PATH.touch()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        sub_resp = AsyncMock()
        sub_resp.json.return_value = sec_submissions_response
        sub_resp.raise_for_status = MagicMock()

        mock_client.get.return_value = sub_resp

        items = await sec_fetcher.fetch("AAPL")

    # submissions 조회 1회만 호출 (CIK 조회 없음)
    assert mock_client.get.call_count == 1
    assert len(items) >= 1
```

- [ ] **Step 2: 테스트 실패 확인**

```
uv run pytest tests/tools/test_disclosure.py::test_sec_fetcher_returns_filtered_filings -v
```
예상: `ImportError: cannot import name 'SECDisclosureFetcher'`

- [ ] **Step 3: `SECDisclosureFetcher` 구현**

`src/tools/disclosure.py` 기존 코드 아래에 추가:

```python
import json
import time
import httpx
from datetime import datetime, timedelta, date
from pathlib import Path


_SEC_USER_AGENT = "invest-jarvis research@example.com"


class SECDisclosureFetcher:
    """미국주식 SEC EDGAR에서 10-Q, 8-K 공시를 조회한다."""

    CIK_URL = "https://www.sec.gov/files/company_tickers.json"
    SUBMISSION_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
    CACHE_PATH = Path("data/cache/sec_cik_cache.json")
    CACHE_TTL = 6 * 3600  # 6시간

    async def fetch(self, ticker: str) -> list[DisclosureItem]:
        """미국 티커에 대한 최근 10-Q/8-K 최대 5건을 반환한다."""
        cik = await self._get_cik(ticker.upper())
        if cik is None:
            return []
        return await self._get_filings(cik)

    async def _get_cik(self, ticker: str) -> int | None:
        cache = self._load_cache()
        if ticker in cache:
            return cache[ticker]

        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": _SEC_USER_AGENT}
        ) as client:
            resp = await client.get(self.CIK_URL)
            resp.raise_for_status()
            data = resp.json()

        mapping: dict[str, int] = {
            entry["ticker"].upper(): entry["cik_str"]
            for entry in data.values()
        }
        self._save_cache(mapping)
        return mapping.get(ticker)

    async def _get_filings(self, cik: int) -> list[DisclosureItem]:
        url = self.SUBMISSION_URL.format(cik=cik)
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": _SEC_USER_AGENT}
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        documents = recent.get("primaryDocument", [])
        accessions = recent.get("accessionNumber", [])

        cutoff = (datetime.now() - timedelta(days=90)).date()
        results: list[DisclosureItem] = []

        for form, date_str, doc, accession in zip(forms, filing_dates, documents, accessions):
            if form not in ("10-Q", "8-K"):
                continue
            if date.fromisoformat(date_str) < cutoff:
                continue

            accession_clean = accession.replace("-", "")
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik}"
                f"/{accession_clean}/{doc}"
            )
            results.append(
                DisclosureItem(
                    form_type=form,
                    date=date_str,
                    description=doc,
                    url=filing_url,
                )
            )
            if len(results) >= 5:
                break

        return results

    def _load_cache(self) -> dict[str, int]:
        if not self.CACHE_PATH.exists():
            return {}
        try:
            mtime = self.CACHE_PATH.stat().st_mtime
            if time.time() - mtime > self.CACHE_TTL:
                return {}
            return json.loads(self.CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_cache(self, mapping: dict[str, int]) -> None:
        self.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.CACHE_PATH.write_text(
            json.dumps(mapping, ensure_ascii=False), encoding="utf-8"
        )
```

- [ ] **Step 4: 테스트 통과 확인**

```
uv run pytest tests/tools/test_disclosure.py -v
```
예상: 전체 통과

- [ ] **Step 5: 커밋**

```bash
git add src/tools/disclosure.py tests/tools/test_disclosure.py
git commit -m "feat: add SECDisclosureFetcher for 10-Q/8-K filings"
```

---

## Task 3: DART 공시 페처

**파일:**
- 수정: `src/tools/disclosure.py`
- 수정: `tests/tools/test_disclosure.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/tools/test_disclosure.py`에 추가:

```python
from src.tools.disclosure import DARTDisclosureFetcher


@pytest.fixture
def dart_fetcher(tmp_path):
    fetcher = DARTDisclosureFetcher(api_key="test_key")
    fetcher.CACHE_PATH = tmp_path / "dart_corp_code_cache.json"
    return fetcher


@pytest.fixture
def dart_corp_response():
    return {"status": "000", "corp_code": "00126380", "corp_name": "삼성전자"}


@pytest.fixture
def dart_list_response():
    return {
        "status": "000",
        "list": [
            {"report_nm": "수주계약 체결", "rcept_dt": "20260405", "rcp_no": "20260405000001"},
            {"report_nm": "분기보고서", "rcept_dt": "20260401", "rcp_no": "20260401000002"},
            {"report_nm": "유상증자결정", "rcept_dt": "20260320", "rcp_no": "20260320000003"},
            {"report_nm": "사업보고서", "rcept_dt": "20260301", "rcp_no": "20260301000004"},
            {"report_nm": "매출계약", "rcept_dt": "20260310", "rcp_no": "20260310000005"},
        ],
    }


@pytest.mark.asyncio
async def test_dart_fetcher_filters_by_score(
    dart_fetcher, dart_corp_response, dart_list_response
):
    """score >= 1.0 인 공시만 반환, score 내림차순 정렬."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        corp_resp = AsyncMock()
        corp_resp.json.return_value = dart_corp_response
        corp_resp.status_code = 200
        corp_resp.raise_for_status = MagicMock()

        list_resp = AsyncMock()
        list_resp.json.return_value = dart_list_response
        list_resp.raise_for_status = MagicMock()

        mock_client.get.side_effect = [corp_resp, list_resp]

        items = await dart_fetcher.fetch("005930")

    # 분기보고서(-1.0), 사업보고서(-1.0)는 임계값 미달로 제외
    report_names = [i.description for i in items]
    assert "분기보고서" not in report_names
    assert "사업보고서" not in report_names
    # 수주계약(1.0), 유상증자결정(1.0), 매출계약(1.0)은 통과
    assert len(items) == 3


@pytest.mark.asyncio
async def test_dart_fetcher_date_formatting(
    dart_fetcher, dart_corp_response, dart_list_response
):
    """YYYYMMDD 날짜를 YYYY-MM-DD 형식으로 변환."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        corp_resp = AsyncMock()
        corp_resp.json.return_value = dart_corp_response
        corp_resp.status_code = 200
        corp_resp.raise_for_status = MagicMock()

        list_resp = AsyncMock()
        list_resp.json.return_value = dart_list_response
        list_resp.raise_for_status = MagicMock()

        mock_client.get.side_effect = [corp_resp, list_resp]

        items = await dart_fetcher.fetch("005930")

    for item in items:
        assert len(item.date) == 10
        assert item.date[4] == "-"
        assert item.date[7] == "-"


@pytest.mark.asyncio
async def test_dart_fetcher_corp_not_found(dart_fetcher):
    """종목코드에 해당하는 corp_code를 찾지 못하면 빈 리스트 반환."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        corp_resp = AsyncMock()
        corp_resp.json.return_value = {"status": "013", "message": "조회된 데이터가 없습니다."}
        corp_resp.status_code = 200
        corp_resp.raise_for_status = MagicMock()

        mock_client.get.return_value = corp_resp

        items = await dart_fetcher.fetch("999999")

    assert items == []


@pytest.mark.asyncio
async def test_dart_fetcher_uses_cache(dart_fetcher, dart_list_response, tmp_path):
    """두 번째 조회 시 파일 캐시를 사용해 corp_code API 재호출을 방지한다."""
    # 캐시 사전 저장: 005930 → 00126380
    cache_data = {"005930": "00126380"}
    dart_fetcher.CACHE_PATH.write_text(json.dumps(cache_data))
    dart_fetcher.CACHE_PATH.touch()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        list_resp = AsyncMock()
        list_resp.json.return_value = dart_list_response
        list_resp.raise_for_status = MagicMock()

        mock_client.get.return_value = list_resp

        items = await dart_fetcher.fetch("005930")

    # list.json 조회 1회만 (company.json corp_code 조회 없음)
    assert mock_client.get.call_count == 1
    assert len(items) > 0
```

- [ ] **Step 2: 테스트 실패 확인**

```
uv run pytest tests/tools/test_disclosure.py::test_dart_fetcher_filters_by_score -v
```
예상: `ImportError: cannot import name 'DARTDisclosureFetcher'`

- [ ] **Step 3: `DARTDisclosureFetcher` 구현**

`src/tools/disclosure.py`에 추가:

```python
_DART_API_BASE = "https://opendart.fss.or.kr/api"

# DART 보고서명 키워드 가중치 테이블
_DART_KEYWORD_WEIGHTS: dict[str, float] = {
    # 고신호 이벤트: 각 키워드 +1.0
    "계약": 1.0,
    "수주": 1.0,
    "실적": 1.0,
    "매출": 1.0,
    "영업이익": 1.0,
    "투자": 1.0,
    "유상증자": 1.0,
    "자기주식": 1.0,
    "소송": 1.0,
    "내부자매도": 1.0,
    # 정기 보고서 (저신호): -1.0
    "사업보고서": -1.0,
    "분기보고서": -1.0,
    "반기보고서": -1.0,
    # 금액 단위 포함 시 소폭 가산
    "조": 0.5,
    "억원": 0.5,
}

_DART_SCORE_THRESHOLD = 1.0
_DART_MAX_RESULTS = 5


def _score_dart_report(report_nm: str) -> float:
    """DART 보고서명으로 관련도 점수 계산."""
    score = 0.0
    for keyword, weight in _DART_KEYWORD_WEIGHTS.items():
        if keyword in report_nm:
            score += weight
    return score


def _fmt_dart_date(rcept_dt: str) -> str:
    """DART 날짜 형식 YYYYMMDD → YYYY-MM-DD 변환."""
    if len(rcept_dt) == 8:
        return f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:]}"
    return rcept_dt


class DARTDisclosureFetcher:
    """OpenDART API로 한국주식 공시를 키워드 필터링하여 조회한다.

    corp_code 조회 결과는 파일 캐시(6시간 TTL)에 저장해
    같은 종목을 반복 분석할 때 불필요한 API 호출을 방지한다.
    """

    CACHE_PATH = Path("data/cache/dart_corp_code_cache.json")
    CACHE_TTL = 6 * 3600  # 6시간

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def fetch(self, stock_code: str) -> list[DisclosureItem]:
        """6자리 KRX 종목코드로 최근 3개월 스코어링된 공시 최대 5건을 반환한다."""
        corp_code = await self._get_corp_code(stock_code)
        if corp_code is None:
            return []

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")

        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bgn_de": start_date,
            "end_de": end_date,
            "page_count": 20,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{_DART_API_BASE}/list.json", params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "000":
            return []

        scored: list[tuple[float, DisclosureItem]] = []
        for item in data.get("list", []):
            report_nm = item.get("report_nm", "")
            score = _score_dart_report(report_nm)
            if score < _DART_SCORE_THRESHOLD:
                continue
            rcp_no = item.get("rcp_no", "")
            disclosure = DisclosureItem(
                form_type="DART",
                date=_fmt_dart_date(item.get("rcept_dt", "")),
                description=report_nm,
                url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp_no}",
                score=score,
            )
            scored.append((score, disclosure))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:_DART_MAX_RESULTS]]

    async def _get_corp_code(self, stock_code: str) -> str | None:
        """KRX 종목코드로 DART 내부 corp_code를 조회한다. 결과를 파일 캐시에 저장한다."""
        # 캐시 확인
        cache = self._load_cache()
        if stock_code in cache:
            return cache[stock_code]

        params = {"crtfc_key": self.api_key, "stock_code": stock_code}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{_DART_API_BASE}/company.json", params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("status") != "000":
                return None
            corp_code = data.get("corp_code")

        if corp_code:
            cache[stock_code] = corp_code
            self._save_cache(cache)

        return corp_code

    def _load_cache(self) -> dict[str, str]:
        if not self.CACHE_PATH.exists():
            return {}
        try:
            mtime = self.CACHE_PATH.stat().st_mtime
            if time.time() - mtime > self.CACHE_TTL:
                return {}
            return json.loads(self.CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_cache(self, mapping: dict[str, str]) -> None:
        self.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.CACHE_PATH.write_text(
            json.dumps(mapping, ensure_ascii=False), encoding="utf-8"
        )
```

- [ ] **Step 4: 테스트 통과 확인**

```
uv run pytest tests/tools/test_disclosure.py -v
```
예상: 전체 통과

- [ ] **Step 5: 커밋**

```bash
git add src/tools/disclosure.py tests/tools/test_disclosure.py
git commit -m "feat: add DARTDisclosureFetcher with keyword scoring"
```

---

## Task 4: `DisclosureTool` 통합 라우터

**파일:**
- 수정: `src/tools/disclosure.py`
- 수정: `tests/tools/test_disclosure.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/tools/test_disclosure.py`에 추가:

```python
from src.tools.disclosure import DisclosureTool
from src.core.models import ToolResult


@pytest.mark.asyncio
async def test_disclosure_tool_routes_us_to_sec():
    """미국 티커는 SEC 페처로 라우팅."""
    mock_sec = AsyncMock()
    mock_sec.fetch.return_value = [
        DisclosureItem(form_type="8-K", date="2026-04-05", description="q1.htm", url="https://sec.gov/...")
    ]
    mock_dart = AsyncMock()

    tool = DisclosureTool(sec_fetcher=mock_sec, dart_fetcher=mock_dart)
    result = await tool.execute("AAPL")

    assert result.success is True
    assert len(result.data) == 1
    mock_sec.fetch.assert_called_once_with("AAPL")
    mock_dart.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_disclosure_tool_routes_kr_to_dart():
    """한국 티커(.KS)는 6자리 코드를 추출하여 DART 페처로 라우팅."""
    mock_sec = AsyncMock()
    mock_dart = AsyncMock()
    mock_dart.fetch.return_value = [
        DisclosureItem(form_type="DART", date="2026-04-05", description="수주계약", url="https://dart.fss.or.kr/...")
    ]

    tool = DisclosureTool(sec_fetcher=mock_sec, dart_fetcher=mock_dart)
    result = await tool.execute("005930.KS")

    assert result.success is True
    mock_dart.fetch.assert_called_once_with("005930")
    mock_sec.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_disclosure_tool_no_dart_fetcher_returns_error():
    """DART 페처 없이 한국주식 조회 시 실패 ToolResult 반환."""
    mock_sec = AsyncMock()

    tool = DisclosureTool(sec_fetcher=mock_sec, dart_fetcher=None)
    result = await tool.execute("005930.KS")

    assert result.success is False
    assert "DART" in result.error


@pytest.mark.asyncio
async def test_disclosure_tool_wraps_exceptions():
    """페처 예외는 실패 ToolResult로 래핑."""
    mock_sec = AsyncMock()
    mock_sec.fetch.side_effect = Exception("network timeout")

    tool = DisclosureTool(sec_fetcher=mock_sec, dart_fetcher=None)
    result = await tool.execute("AAPL")

    assert result.success is False
    assert "network timeout" in result.error
```

- [ ] **Step 2: 테스트 실패 확인**

```
uv run pytest tests/tools/test_disclosure.py::test_disclosure_tool_routes_us_to_sec -v
```
예상: `ImportError: cannot import name 'DisclosureTool'`

- [ ] **Step 3: `DisclosureTool` 구현**

`src/tools/disclosure.py`에 추가:

```python
from src.core.models import ToolResult


class DisclosureTool:
    """티커 형식에 따라 SEC(미국) 또는 DART(한국)로 공시 조회를 라우팅한다."""

    def __init__(
        self,
        sec_fetcher: SECDisclosureFetcher,
        dart_fetcher: DARTDisclosureFetcher | None = None,
    ) -> None:
        self.sec_fetcher = sec_fetcher
        self.dart_fetcher = dart_fetcher

    async def execute(self, ticker: str) -> ToolResult:
        """주어진 티커의 공시를 조회한다. ToolResult[list[DisclosureItem]] 반환."""
        try:
            if is_korean_ticker(ticker):
                if self.dart_fetcher is None:
                    return ToolResult(
                        success=False,
                        data=None,
                        error="DART 페처 미설정 — OPENDART_API_KEY를 환경변수에 추가하세요",
                    )
                code = extract_kr_code(ticker)
                items = await self.dart_fetcher.fetch(code)
            else:
                items = await self.sec_fetcher.fetch(ticker)
            return ToolResult(success=True, data=items)
        except Exception as exc:
            return ToolResult(success=False, data=None, error=str(exc))
```

- [ ] **Step 4: 전체 disclosure 테스트 실행**

```
uv run pytest tests/tools/test_disclosure.py -v
```
예상: 전체 통과

- [ ] **Step 5: 커밋**

```bash
git add src/tools/disclosure.py tests/tools/test_disclosure.py
git commit -m "feat: add DisclosureTool router (SEC for US, DART for Korean stocks)"
```

---

## Task 5: `InvestorFlow` 모델 + `FlowTool`

**파일:**
- 신규: `src/tools/flow.py`
- 신규: `tests/tools/test_flow.py`

`FlowTool`은 이미 구현된 `KISProvider.get_investor_trend()` (`src/providers/kis.py:330`)를 래핑한다. **10일치**를 가져와 1일·5일·10일 구간별 방향 판단 + 10일 중 순매수 일수를 제공한다.

`get_investor_trend(ticker, days=10)` 반환 형식 (최신일이 index 0):
```python
[{"date": "20260411", "foreign_net": 850, "institution_net": 320, "total_net": 1170}, ...]
```

**`InvestorFlow` 제공 정보:**

| 속성 | 설명 |
|------|------|
| `foreign_direction_1d` | 최신 1일 외인 방향 ("매수"/"매도") |
| `foreign_direction_5d` | 최근 5일 과반 기준 외인 방향 |
| `foreign_direction_10d` | 전체 10일 과반 기준 외인 방향 |
| `foreign_buy_days` | 10일 중 외인 순매수 일수 (예: 7) |
| `institution_direction_1d` | 최신 1일 기관 방향 |
| `institution_direction_5d` | 최근 5일 과반 기준 기관 방향 |
| `institution_direction_10d` | 전체 10일 과반 기준 기관 방향 |
| `institution_buy_days` | 10일 중 기관 순매수 일수 |
| `foreign_net_1d` / `_5d` / `_10d` | 각 구간 외인 순매수 합계 |
| `institution_net_1d` / `_5d` / `_10d` | 각 구간 기관 순매수 합계 |

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/tools/test_flow.py
import pytest
from unittest.mock import AsyncMock
from src.tools.flow import InvestorFlowEntry, InvestorFlow, FlowTool
from src.core.models import ToolResult


# 10일치 샘플 데이터 (최신일이 index 0)
SAMPLE_10D = [
    {"date": "20260411", "foreign_net":  500, "institution_net":  300, "total_net":  800},
    {"date": "20260410", "foreign_net": -200, "institution_net":  100, "total_net": -100},
    {"date": "20260409", "foreign_net":  300, "institution_net": -150, "total_net":  150},
    {"date": "20260408", "foreign_net":  400, "institution_net":  200, "total_net":  600},
    {"date": "20260407", "foreign_net": -100, "institution_net": -200, "total_net": -300},
    {"date": "20260404", "foreign_net":  200, "institution_net":  100, "total_net":  300},
    {"date": "20260403", "foreign_net": -300, "institution_net":  250, "total_net":  -50},
    {"date": "20260402", "foreign_net":  150, "institution_net": -100, "total_net":   50},
    {"date": "20260401", "foreign_net":  100, "institution_net":  200, "total_net":  300},
    {"date": "20260331", "foreign_net": -400, "institution_net": -300, "total_net": -700},
]


def test_investor_flow_entry_creation():
    entry = InvestorFlowEntry(date="2026-04-11", foreign_net=320, institution_net=850)
    assert entry.foreign_net == 320
    assert entry.institution_net == 850


def _make_flow(raw: list[dict]) -> InvestorFlow:
    entries = [
        InvestorFlowEntry(
            date=f"{d['date'][:4]}-{d['date'][4:6]}-{d['date'][6:]}",
            foreign_net=d["foreign_net"],
            institution_net=d["institution_net"],
        )
        for d in raw
    ]
    return InvestorFlow(code="005930", entries=entries)


# ── 1일 방향 ──────────────────────────────────────────────────────────────────

def test_foreign_direction_1d_buy():
    flow = _make_flow(SAMPLE_10D)
    # 최신일(index 0) foreign_net=500 → 매수
    assert flow.foreign_direction_1d == "매수"


def test_institution_direction_1d_buy():
    flow = _make_flow(SAMPLE_10D)
    # 최신일(index 0) institution_net=300 → 매수
    assert flow.institution_direction_1d == "매수"


# ── 5일 방향 ──────────────────────────────────────────────────────────────────

def test_foreign_direction_5d():
    flow = _make_flow(SAMPLE_10D)
    # 최근 5일: 500, -200, 300, 400, -100 → 순매수 3일, 순매도 2일 → 매수
    assert flow.foreign_direction_5d == "매수"


def test_institution_direction_5d():
    flow = _make_flow(SAMPLE_10D)
    # 최근 5일: 300, 100, -150, 200, -200 → 순매수 3일, 순매도 2일 → 매수
    assert flow.institution_direction_5d == "매수"


# ── 10일 방향 ─────────────────────────────────────────────────────────────────

def test_foreign_direction_10d():
    flow = _make_flow(SAMPLE_10D)
    # 10일: 500,-200,300,400,-100,200,-300,150,100,-400
    # 순매수일: 500,300,400,200,150,100 = 6일 → 매수
    assert flow.foreign_direction_10d == "매수"


def test_institution_direction_10d():
    flow = _make_flow(SAMPLE_10D)
    # 10일: 300,100,-150,200,-200,100,250,-100,200,-300
    # 순매수일: 300,100,200,100,250,200 = 6일 → 매수
    assert flow.institution_direction_10d == "매수"


# ── 순매수 일수 ───────────────────────────────────────────────────────────────

def test_foreign_buy_days():
    flow = _make_flow(SAMPLE_10D)
    # 500,300,400,200,150,100 = 6일
    assert flow.foreign_buy_days == 6


def test_institution_buy_days():
    flow = _make_flow(SAMPLE_10D)
    # 300,100,200,100,250,200 = 6일
    assert flow.institution_buy_days == 6


# ── 구간별 순매수 합계 ─────────────────────────────────────────────────────────

def test_foreign_net_1d():
    flow = _make_flow(SAMPLE_10D)
    assert flow.foreign_net_1d == 500


def test_foreign_net_5d():
    flow = _make_flow(SAMPLE_10D)
    assert flow.foreign_net_5d == 500 + (-200) + 300 + 400 + (-100)  # 900


def test_foreign_net_10d():
    flow = _make_flow(SAMPLE_10D)
    assert flow.foreign_net_10d == sum(d["foreign_net"] for d in SAMPLE_10D)  # 750


def test_institution_net_5d():
    flow = _make_flow(SAMPLE_10D)
    assert flow.institution_net_5d == 300 + 100 + (-150) + 200 + (-200)  # 250


# ── FlowTool ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flow_tool_fetches_10_days():
    """FlowTool이 days=10으로 KIS API를 호출한다."""
    mock_kis = AsyncMock()
    mock_kis.get_investor_trend.return_value = SAMPLE_10D

    tool = FlowTool(kis_provider=mock_kis)
    result = await tool.execute("005930")

    assert result.success is True
    flow: InvestorFlow = result.data
    assert flow.code == "005930"
    assert len(flow.entries) == 10
    assert flow.entries[0].date == "2026-04-11"
    assert flow.entries[0].foreign_net == 500
    mock_kis.get_investor_trend.assert_called_once_with("005930", days=10)


@pytest.mark.asyncio
async def test_flow_tool_kis_error_returns_failed_result():
    """KIS API 오류 시 ToolResult(success=False) 반환."""
    mock_kis = AsyncMock()
    mock_kis.get_investor_trend.side_effect = Exception("KIS API unauthorized")

    tool = FlowTool(kis_provider=mock_kis)
    result = await tool.execute("005930")

    assert result.success is False
    assert "KIS API unauthorized" in result.error


@pytest.mark.asyncio
async def test_flow_tool_no_kis_provider_returns_failed_result():
    """KISProvider 미설정 시 실패 ToolResult 반환."""
    tool = FlowTool(kis_provider=None)
    result = await tool.execute("005930")

    assert result.success is False
    assert "KIS" in result.error
```

- [ ] **Step 2: 테스트 실패 확인**

```
uv run pytest tests/tools/test_flow.py -v
```
예상: `ModuleNotFoundError: No module named 'src.tools.flow'`

- [ ] **Step 3: `flow.py` 구현**

```python
# src/tools/flow.py
"""
KIS API 수급 툴 — 한국주식의 외인/기관 일별 순매수 데이터를 조회한다.

KISProvider.get_investor_trend()를 래핑하여 10일치 InvestorFlow 모델을 생성한다.
1일·5일·10일 구간별 방향 판단 및 10일 중 순매수 일수를 제공한다.
"""
from dataclasses import dataclass, field
from src.core.models import ToolResult


def _fmt_kis_date(date_str: str) -> str:
    """KIS 날짜 형식 YYYYMMDD → YYYY-MM-DD 변환."""
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str


def _direction(entries: list, attr: str) -> str:
    """주어진 entries 구간에서 attr(foreign_net or institution_net) 과반 기준 방향 반환."""
    if not entries:
        return "N/A"
    buys = sum(1 for e in entries if getattr(e, attr) > 0)
    return "매수" if buys > len(entries) / 2 else "매도"


def _net_sum(entries: list, attr: str) -> int:
    """주어진 entries 구간의 attr 합계."""
    return sum(getattr(e, attr) for e in entries)


@dataclass
class InvestorFlowEntry:
    """하루치 투자자 순매수 데이터 (KIS API 기준, 단위: 주)."""

    date: str            # "YYYY-MM-DD", 최신일이 index 0
    foreign_net: int     # 양수=순매수, 음수=순매도
    institution_net: int


@dataclass
class InvestorFlow:
    """한국주식 10일 수급 요약. entries[0]이 가장 최신일."""

    code: str
    entries: list[InvestorFlowEntry] = field(default_factory=list)

    # ── 1일 방향 (최신 하루) ────────────────────────────────────────────────────

    @property
    def foreign_direction_1d(self) -> str:
        return _direction(self.entries[:1], "foreign_net")

    @property
    def institution_direction_1d(self) -> str:
        return _direction(self.entries[:1], "institution_net")

    # ── 5일 방향 ────────────────────────────────────────────────────────────────

    @property
    def foreign_direction_5d(self) -> str:
        return _direction(self.entries[:5], "foreign_net")

    @property
    def institution_direction_5d(self) -> str:
        return _direction(self.entries[:5], "institution_net")

    # ── 10일 방향 ───────────────────────────────────────────────────────────────

    @property
    def foreign_direction_10d(self) -> str:
        return _direction(self.entries, "foreign_net")

    @property
    def institution_direction_10d(self) -> str:
        return _direction(self.entries, "institution_net")

    # ── 10일 중 순매수 일수 ─────────────────────────────────────────────────────

    @property
    def foreign_buy_days(self) -> int:
        """10일 중 외인 순매수 일수."""
        return sum(1 for e in self.entries if e.foreign_net > 0)

    @property
    def institution_buy_days(self) -> int:
        """10일 중 기관 순매수 일수."""
        return sum(1 for e in self.entries if e.institution_net > 0)

    # ── 구간별 순매수 합계 ──────────────────────────────────────────────────────

    @property
    def foreign_net_1d(self) -> int:
        return _net_sum(self.entries[:1], "foreign_net")

    @property
    def foreign_net_5d(self) -> int:
        return _net_sum(self.entries[:5], "foreign_net")

    @property
    def foreign_net_10d(self) -> int:
        return _net_sum(self.entries, "foreign_net")

    @property
    def institution_net_1d(self) -> int:
        return _net_sum(self.entries[:1], "institution_net")

    @property
    def institution_net_5d(self) -> int:
        return _net_sum(self.entries[:5], "institution_net")

    @property
    def institution_net_10d(self) -> int:
        return _net_sum(self.entries, "institution_net")


class FlowTool:
    """KISProvider를 통해 한국주식 10일 수급 데이터를 조회한다."""

    def __init__(self, kis_provider) -> None:
        """
        Args:
            kis_provider: KISProvider 인스턴스. KIS 키 미설정 시 None.
        """
        self.kis_provider = kis_provider

    async def execute(self, code: str) -> ToolResult:
        """6자리 KRX 종목코드로 10일 수급 데이터를 조회한다.

        Returns:
            ToolResult[InvestorFlow] on success, ToolResult(success=False) on error.
        """
        if self.kis_provider is None:
            return ToolResult(
                success=False,
                data=None,
                error="KIS provider 미설정 — KIS_APP_KEY, KIS_APP_SECRET 환경변수를 확인하세요",
            )
        try:
            raw = await self.kis_provider.get_investor_trend(code, days=10)
            entries = [
                InvestorFlowEntry(
                    date=_fmt_kis_date(item["date"]),
                    foreign_net=item["foreign_net"],
                    institution_net=item["institution_net"],
                )
                for item in raw
            ]
            return ToolResult(success=True, data=InvestorFlow(code=code, entries=entries))
        except Exception as exc:
            return ToolResult(success=False, data=None, error=str(exc))
```

- [ ] **Step 4: 테스트 통과 확인**

```
uv run pytest tests/tools/test_flow.py -v
```
예상: 전체 통과

- [ ] **Step 5: 커밋**

```bash
git add src/tools/flow.py tests/tools/test_flow.py
git commit -m "feat: add FlowTool with 10-day 1d/5d/10d investor flow analysis"
```

---

## Task 6: `DeepDivePipeline` 통합

**파일:**
- 수정: `src/pipelines/deep_dive.py`
- 수정: `tests/pipelines/test_deep_dive.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/pipelines/test_deep_dive.py`에 추가:

```python
from unittest.mock import AsyncMock
from src.tools.disclosure import DisclosureItem
from src.tools.flow import InvestorFlow, InvestorFlowEntry
from src.llm.models import IntegratedAnalysisOutput


@pytest.fixture
def mock_disclosure_tool():
    tool = AsyncMock()
    tool.execute.return_value = ToolResult(
        success=True,
        data=[
            DisclosureItem(
                form_type="8-K",
                date="2026-04-05",
                description="q1.htm",
                url="https://sec.gov/...",
            )
        ],
    )
    return tool


@pytest.mark.asyncio
async def test_deep_dive_includes_disclosure_in_result(
    mock_technical_tool, mock_news_tool, mock_llm, mock_disclosure_tool
):
    """disclosure_tool 주입 시 결과 dict에 'disclosure' 키가 포함된다."""
    with patch("src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock) as mock_ts:
        with patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_na:
            with patch("src.llm.analyzer.generate_integrated_analysis", new_callable=AsyncMock) as mock_ia:
                mock_ts.return_value = TechnicalSummaryOutput(
                    summary="강세", key_insights=[], recommendation="매수",
                    confidence=0.75, rationale="좋음",
                )
                mock_na.return_value = NewsAnalysisOutput(
                    sentiment="긍정", confidence=0.8, key_themes=[],
                    summary="긍정적", impact_assessment="좋음",
                )
                mock_ia.return_value = IntegratedAnalysisOutput(
                    recommendation="매수",
                    rationale=["기술적: 상승 추세"],
                    risks=["RSI 과열"],
                    action_summary="매수 추천",
                )

                pipeline = DeepDivePipeline(
                    technical_tool=mock_technical_tool,
                    news_tool=mock_news_tool,
                    llm=mock_llm,
                    disclosure_tool=mock_disclosure_tool,
                )

                result = await pipeline.run("AAPL")

    assert "disclosure" in result
    assert len(result["disclosure"]) == 1
    assert result["disclosure"][0].form_type == "8-K"


@pytest.mark.asyncio
async def test_deep_dive_disclosure_failure_does_not_raise(
    mock_technical_tool, mock_news_tool, mock_llm
):
    """disclosure_tool 실패 시에도 파이프라인이 정상 완료된다."""
    bad_disclosure_tool = AsyncMock()
    bad_disclosure_tool.execute.return_value = ToolResult(
        success=False, data=None, error="API error"
    )

    with patch("src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock) as mock_ts:
        with patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_na:
            mock_ts.return_value = TechnicalSummaryOutput(
                summary="강세", key_insights=[], recommendation="매수",
                confidence=0.75, rationale="좋음",
            )
            mock_na.return_value = NewsAnalysisOutput(
                sentiment="긍정", confidence=0.8, key_themes=[],
                summary="긍정적", impact_assessment="좋음",
            )

            pipeline = DeepDivePipeline(
                technical_tool=mock_technical_tool,
                news_tool=mock_news_tool,
                llm=mock_llm,
                disclosure_tool=bad_disclosure_tool,
            )

            result = await pipeline.run("AAPL")

    # 공시 실패는 조용히 처리됨
    assert result["disclosure"] is None
    assert result["ticker"] == "AAPL"
```

- [ ] **Step 2: 테스트 실패 확인**

```
uv run pytest tests/pipelines/test_deep_dive.py::test_deep_dive_includes_disclosure_in_result -v
```
예상: `TypeError: DeepDivePipeline.__init__() got an unexpected keyword argument 'disclosure_tool'`

- [ ] **Step 3: `DeepDivePipeline` 최소 변경**

기존 파일의 인터페이스를 유지하면서 필요한 부분만 수정한다. 전체 파일 교체 대신 세 곳만 Edit:

- [ ] **Step 3-1: `__init__` 파라미터에 optional 툴 추가**

파일 상단에 신규 임포트 추가:

```python
from src.tools.disclosure import DisclosureTool, DisclosureItem, is_korean_ticker, extract_kr_code
from src.tools.flow import FlowTool, InvestorFlow
from src.llm.models import IntegratedAnalysisInput, IntegratedAnalysisOutput
```

`DeepDivePipeline.__init__()` 시그니처에 optional 파라미터 추가:

```python
def __init__(
    self,
    technical_tool: TechnicalAnalysisTool,
    news_tool: NewsTool,
    llm: BaseChatModel,
    fundamental_tool: FundamentalTool | None = None,
    disclosure_tool: DisclosureTool | None = None,  # 신규
    flow_tool: FlowTool | None = None,              # 신규
):
    self.technical_tool = technical_tool
    self.news_tool = news_tool
    self.llm = llm
    self.fundamental_tool = fundamental_tool
    self.disclosure_tool = disclosure_tool  # 신규
    self.flow_tool = flow_tool              # 신규
```

- [ ] **Step 3-2: `run()` 메서드에 선택적 툴 병렬 실행 추가**

`run()` 메서드 중간에 뉴스 fetching 다음, LLM 분석 이전 위치에 삽입:

```python
# 선택적 툴 병렬 실행
optional_coros = []
optional_keys: list[str] = []

if self.disclosure_tool:
    optional_coros.append(self.disclosure_tool.execute(ticker))
    optional_keys.append("disclosure")

if self.flow_tool and is_korean_ticker(ticker):
    optional_coros.append(self.flow_tool.execute(extract_kr_code(ticker)))
    optional_keys.append("flow")

optional_data: dict = {}
if optional_coros:
    opt_results = await asyncio.gather(*optional_coros, return_exceptions=True)
    for key, res in zip(optional_keys, opt_results):
        if not isinstance(res, Exception) and res.success:
            optional_data[key] = res.data
        else:
            logger.warning("선택적 툴 '%s' 실패: %s", key, res)
            optional_data[key] = None

disclosure_items: list[DisclosureItem] | None = optional_data.get("disclosure")
flow_data: InvestorFlow | None = optional_data.get("flow")
```

- [ ] **Step 3-3: integrated_analysis 생성 및 반환 dict 확장**

`run()` 메서드의 return 문 이전에 종합 분석 로직 추가:

```python
# 공시 또는 수급 데이터가 있을 때만 종합 인사이트 생성
integrated_analysis = None
if disclosure_items is not None or flow_data is not None:
    integrated_analysis = await self._generate_integrated_analysis(
        ticker=ticker,
        technical_summary=technical_summary,
        fundamental_summary=fundamental_summary,
        disclosure_items=disclosure_items,
        flow_data=flow_data,
    )
```

return dict에 세 키 추가:

```python
return {
    # ... 기존 키들 ...
    "disclosure": disclosure_items,
    "flow": flow_data,
    "integrated_analysis": integrated_analysis,
}
```

`_generate_integrated_analysis()` 헬퍼 메서드 추가:

```python
def _format_flow_for_llm(flow: InvestorFlow) -> str:
    """InvestorFlow를 LLM 컨텍스트용 마크다운 테이블 문자열로 변환."""
    lines = [
        "| 투자자 | 1일 | 5일 | 10일 | 10일 순매수 일수 |",
        "|--------|-----|-----|------|-----------------|",
        (
            f"| 외국인 "
            f"| {flow.foreign_direction_1d} ({flow.foreign_net_1d:+,}) "
            f"| {flow.foreign_direction_5d} ({flow.foreign_net_5d:+,}) "
            f"| {flow.foreign_direction_10d} ({flow.foreign_net_10d:+,}) "
            f"| {flow.foreign_buy_days}/10일 |"
        ),
        (
            f"| 기관 "
            f"| {flow.institution_direction_1d} ({flow.institution_net_1d:+,}) "
            f"| {flow.institution_direction_5d} ({flow.institution_net_5d:+,}) "
            f"| {flow.institution_direction_10d} ({flow.institution_net_10d:+,}) "
            f"| {flow.institution_buy_days}/10일 |"
        ),
    ]
    return "\n".join(lines)


async def _generate_integrated_analysis(
    self,
    ticker: str,
    technical_summary: TechnicalSummaryOutput,
    fundamental_summary: FundamentalSummaryOutput | None,
    disclosure_items: list[DisclosureItem] | None,
    flow_data: InvestorFlow | None,
) -> IntegratedAnalysisOutput:
    input_data = IntegratedAnalysisInput(
        ticker=ticker,
        technical_recommendation=technical_summary.recommendation,
        technical_rationale=technical_summary.rationale,
        fundamental_valuation=(
            fundamental_summary.valuation_assessment if fundamental_summary else None
        ),
        disclosure_items=disclosure_items or [],  # 강타입: 직접 전달
        flow_summary=_format_flow_for_llm(flow_data) if flow_data else None,
    )
    return await analyzer.generate_integrated_analysis(input_data, self.llm)
```

- [ ] **Step 4: 파이프라인 테스트 전체 실행**

```
uv run pytest tests/pipelines/test_deep_dive.py -v
```
예상: 전체 통과

- [ ] **Step 5: 커밋**

```bash
git add src/pipelines/deep_dive.py tests/pipelines/test_deep_dive.py
git commit -m "feat: integrate DisclosureTool and FlowTool into DeepDivePipeline"
```

---

## Task 7: LLM 모델 + `generate_integrated_analysis()`

**파일:**
- 수정: `src/llm/models.py`
- 수정: `src/llm/analyzer.py`
- 수정: `tests/llm/test_analyzer.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/llm/test_analyzer.py`에 추가:

```python
from unittest.mock import AsyncMock, MagicMock, patch
from src.llm.analyzer import generate_integrated_analysis
from src.llm.models import IntegratedAnalysisInput, IntegratedAnalysisOutput


@pytest.mark.asyncio
async def test_generate_integrated_analysis_calls_llm():
    """generate_integrated_analysis가 모든 팩터를 LLM에 전달하고 구조화된 결과를 반환한다."""
    mock_llm = AsyncMock()
    expected_output = IntegratedAnalysisOutput(
        recommendation="매수",
        rationale=["기술적: 골든크로스", "공시: 수주계약 체결"],
        risks=["RSI 과열 구간 접근"],
        action_summary="단기 매수 기회 포착",
    )

    with patch("src.llm.analyzer.ChatPromptTemplate") as mock_template:
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = expected_output
        mock_template.from_messages.return_value.__or__ = MagicMock(return_value=mock_chain)

        input_data = IntegratedAnalysisInput(
            ticker="AAPL",
            technical_recommendation="매수",
            technical_rationale="골든크로스 발생",
            fundamental_valuation="저평가",
            disclosure_items=[
                {"form_type": "8-K", "date": "2026-04-05", "description": "Q1 results", "url": "https://sec.gov/..."}
            ],
            flow_summary=None,
        )

        result = await generate_integrated_analysis(input_data, mock_llm)

    assert result.recommendation == "매수"
    assert len(result.rationale) == 2
    assert result.action_summary == "단기 매수 기회 포착"
```

- [ ] **Step 2: 테스트 실패 확인**

```
uv run pytest tests/llm/test_analyzer.py::test_generate_integrated_analysis_calls_llm -v
```
예상: `ImportError: cannot import name 'IntegratedAnalysisInput'`

- [ ] **Step 3: `src/llm/models.py`에 신규 모델 추가**

파일 상단 임포트에 DisclosureItem 추가:

```python
from src.tools.disclosure import DisclosureItem
```

파일 끝에 추가:

```python
# 종합 분석 I/O
class IntegratedAnalysisInput(BaseModel):
    """멀티팩터 종합 분석 입력."""
    ticker: str
    technical_recommendation: str        # "매수", "매도", "중립"
    technical_rationale: str             # 기술적 분석 근거 자유 형식
    fundamental_valuation: str | None = None   # "저평가", "적정", "고평가"
    disclosure_items: list[DisclosureItem] = []  # 강타입: Pydantic 모델 리스트
    flow_summary: str | None = None      # 사전 포맷된 마크다운 테이블 또는 None


class IntegratedAnalysisOutput(BaseModel):
    """멀티팩터 종합 분석 출력."""
    recommendation: str        # "매수", "매도", "중립"
    rationale: list[str]       # 3-4개 근거, 각 항목은 "기술적:" / "기본적:" / "공시:" / "수급:" 접두사
    risks: list[str]           # 2-3개 리스크 요인
    action_summary: str        # 한 줄 한국어 요약
```

- [ ] **Step 4: `src/llm/analyzer.py`에 `generate_integrated_analysis()` 추가**

파일 끝에 추가:

```python
from src.llm.models import IntegratedAnalysisInput, IntegratedAnalysisOutput


async def generate_integrated_analysis(
    input_data: IntegratedAnalysisInput,
    llm: BaseChatModel,
) -> IntegratedAnalysisOutput:
    """기술적·기본적·공시·수급 팩터를 통합한 종합 투자 분석을 생성한다."""
    disclosure_text = "\n".join(
        f"- [{d['form_type']}] {d['date']}: {d['description']}\n  URL: {d['url']}"
        for d in input_data.disclosure_items
    ) if input_data.disclosure_items else "해당 기간 주요 공시 없음"

    flow_text = input_data.flow_summary or "수급 데이터 없음 (미국주식 또는 KIS 미설정)"

    prompt = ChatPromptTemplate.from_messages([
        ("system", "당신은 한국 주식시장 종합 분석 전문가입니다. 실행 가능한 투자 인사이트를 제공하세요."),
        ("user", """종합 투자 분석을 제공하세요. 종목: {ticker}

**기술적 분석**: {technical_recommendation} — {technical_rationale}

**기본적 분석 (밸류에이션)**: {fundamental_valuation}

**공시 분석 (최근 3개월)**:
{disclosure_text}

**수급 동향**:
{flow_text}

다음 형식으로 분석하세요:
- recommendation: "매수", "매도", 또는 "중립"
- rationale: 3-4개 근거 (각 항목은 "기술적:", "기본적:", "공시:", "수급:" 중 하나로 시작)
- risks: 2-3개 리스크 요인
- action_summary: 한 줄 요약"""),
    ])

    chain = prompt | llm.with_structured_output(IntegratedAnalysisOutput)

    return await chain.ainvoke({
        "ticker": input_data.ticker,
        "technical_recommendation": input_data.technical_recommendation,
        "technical_rationale": input_data.technical_rationale,
        "fundamental_valuation": input_data.fundamental_valuation or "N/A",
        "disclosure_text": disclosure_text,
        "flow_text": flow_text,
    })
```

- [ ] **Step 5: 테스트 통과 확인**

```
uv run pytest tests/llm/ tests/pipelines/test_deep_dive.py -v
```
예상: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add src/llm/models.py src/llm/analyzer.py tests/llm/test_analyzer.py
git commit -m "feat: add IntegratedAnalysisOutput model and generate_integrated_analysis LLM function"
```

---

## Task 8: `format_deep_dive_output()` 출력 포매팅

**파일:**
- 수정: `src/cli/main.py`

> 순수 포매팅 코드는 별도 유닛 테스트 없이 기존 CLI/파이프라인 테스트로 커버한다.

- [ ] **Step 1: `format_deep_dive_output()` 함수 끝부분 수정**

`src/cli/main.py`의 `format_deep_dive_output()` 마지막 `return output` 직전을 찾아 아래로 교체:

```python
    if news_analysis:
        output += "## News Analysis\n\n"
        output += f"**Sentiment**: {news_analysis.sentiment} (신뢰도: {news_analysis.confidence * 100:.0f}%)\n\n"
        output += f"**Summary**: {news_analysis.summary}\n\n"
        output += f"**Impact Assessment**: {news_analysis.impact_assessment}\n\n"

        if news_analysis.key_themes:
            output += "**Key Themes**: " + ", ".join(news_analysis.key_themes) + "\n\n"

    # ── 신규 섹션 ──────────────────────────────────────────────────────────────

    disclosure = result.get("disclosure")
    if disclosure:
        output += "## 공시 분석\n\n"
        output += f"최근 3개월 주요 공시 {len(disclosure)}건:\n\n"
        for i, item in enumerate(disclosure, 1):
            output += f"{i}. **[{item.form_type}] {item.description}** ({item.date})\n"
            output += f"   → [공시 원문 보기]({item.url})\n\n"

    flow = result.get("flow")
    if flow:
        output += "## 수급 동향\n\n"
        output += "| 투자자 | 1일 | 5일 | 10일 | 10일 순매수 일수 |\n"
        output += "|--------|-----|-----|------|------------------|\n"
        output += (
            f"| 외국인 "
            f"| {flow.foreign_direction_1d} ({flow.foreign_net_1d:+,}) "
            f"| {flow.foreign_direction_5d} ({flow.foreign_net_5d:+,}) "
            f"| {flow.foreign_direction_10d} ({flow.foreign_net_10d:+,}) "
            f"| {flow.foreign_buy_days}/10일 |\n"
        )
        output += (
            f"| 기관 "
            f"| {flow.institution_direction_1d} ({flow.institution_net_1d:+,}) "
            f"| {flow.institution_direction_5d} ({flow.institution_net_5d:+,}) "
            f"| {flow.institution_direction_10d} ({flow.institution_net_10d:+,}) "
            f"| {flow.institution_buy_days}/10일 |\n"
        )
        output += "\n"

    integrated = result.get("integrated_analysis")
    if integrated:
        output += "## 종합 인사이트\n\n"
        output += f"**투자 추천**: {integrated.recommendation}\n\n"
        output += f"**액션**: {integrated.action_summary}\n\n"
        if integrated.rationale:
            output += "**근거**:\n"
            for r in integrated.rationale:
                output += f"- {r}\n"
            output += "\n"
        if integrated.risks:
            output += "**리스크**:\n"
            for r in integrated.risks:
                output += f"- {r}\n"
            output += "\n"

    return output
```

- [ ] **Step 2: 기존 테스트가 깨지지 않는지 확인**

```
uv run pytest tests/pipelines/test_deep_dive.py tests/cli/ -v
```
예상: 전체 통과

- [ ] **Step 3: 커밋**

```bash
git add src/cli/main.py
git commit -m "feat: render 공시/수급/종합인사이트 sections in analyze output"
```

---

## Task 9: CLI 연결 — `run_deep_dive()`에 신규 툴 주입

**파일:**
- 수정: `src/cli/main.py`

- [ ] **Step 1: `src/cli/main.py` 상단 임포트에 신규 툴 추가**

기존 임포트 블록 (약 86-104행) 에서 `from src.tools.screener.universe import UniverseBuilder` 아래에 추가:

```python
from src.tools.disclosure import DisclosureTool, SECDisclosureFetcher, DARTDisclosureFetcher
from src.tools.flow import FlowTool
```

- [ ] **Step 2: `run_deep_dive()` 함수 전체 교체**

```python
async def run_deep_dive(ticker_or_name: str, provider: str) -> dict:
    """심층 분석 파이프라인 실행."""
    ticker = await resolve_ticker(ticker_or_name)

    api_key_env = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    base_url_env = "OPENAI_BASE_URL" if provider == "openai" else "ANTHROPIC_BASE_URL"
    api_key = os.getenv(api_key_env)
    base_url = os.getenv(base_url_env)
    if not api_key:
        raise ValueError(f"Missing {api_key_env} environment variable")

    yf_provider = YFinanceProvider()
    scorer = TechnicalScorer()
    technical_tool = TechnicalAnalysisTool(provider=yf_provider, scorer=scorer)
    fundamental_tool = FundamentalTool()
    news_tool = NewsTool()
    llm = LLMProvider.create(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )

    # 공시 툴: SEC는 항상 사용 가능, DART는 API 키 있을 때만
    sec_fetcher = SECDisclosureFetcher()
    opendart_key = os.getenv("OPENDART_API_KEY")
    if not opendart_key:
        logger.warning(
            "OPENDART_API_KEY가 설정되지 않았습니다. "
            "한국주식 공시 데이터가 제외됩니다."
        )
    dart_fetcher = DARTDisclosureFetcher(api_key=opendart_key) if opendart_key else None
    disclosure_tool = DisclosureTool(sec_fetcher=sec_fetcher, dart_fetcher=dart_fetcher)

    # 수급 툴: KIS API (get_investor_trend) 사용. 키 없으면 FlowTool이 graceful failure 처리
    kis_key = os.getenv("KIS_APP_KEY")
    kis_secret = os.getenv("KIS_APP_SECRET")
    if not (kis_key and kis_secret):
        logger.warning(
            "KIS_APP_KEY 또는 KIS_APP_SECRET이 설정되지 않았습니다. "
            "한국주식 수급 데이터가 제외됩니다."
        )
    kis_provider = (
        KISProvider(app_key=kis_key, app_secret=kis_secret)
        if kis_key and kis_secret
        else None
    )
    flow_tool = FlowTool(kis_provider=kis_provider)

    pipeline = DeepDivePipeline(
        technical_tool=technical_tool,
        news_tool=news_tool,
        llm=llm,
        fundamental_tool=fundamental_tool,
        disclosure_tool=disclosure_tool,
        flow_tool=flow_tool,
    )

    return await pipeline.run(ticker)
```

- [ ] **Step 3: 전체 테스트 스위트 실행**

```
uv run pytest -v
```
예상: 전체 통과 (신규 툴은 주입되지 않은 테스트에서 조용히 무시됨)

- [ ] **Step 4: 커밋**

```bash
git add src/cli/main.py
git commit -m "feat: wire DisclosureTool and FlowTool into jarvis analyze CLI command"
```

---

## Task 10: 문서 업데이트

**파일:**
- 수정: `README.md`
- 수정: `docs/CLI_USAGE.md`
- 수정: `CLAUDE.md` (아키텍처 섹션)

- [ ] **Step 1: `README.md` Features 섹션에 추가**

```markdown
- **공시 분석**: SEC EDGAR 10-Q/8-K (미국주식) + OpenDART 키워드 필터링 (한국주식) — 최근 3개월
- **수급 동향**: 외국인/기관 순매수 5일 추이 (한국주식, KIS OpenAPI)
- **종합 인사이트**: 기술적 + 기본적 + 공시 + 수급 통합 LLM 분석
```

- [ ] **Step 2: `README.md` 환경변수 섹션에 추가**

```
OPENDART_API_KEY=...    # 한국주식 공시 조회용 (선택)
```

- [ ] **Step 3: `docs/CLI_USAGE.md` — analyze 커맨드 출력 내용 업데이트**

`### 2. analyze` 섹션의 **출력 내용** 에 추가:

```markdown
- **공시 분석** (최근 3개월 주요 공시, SEC/DART)         ← 신규
- **수급 동향** (외인/기관 5일 순매수, 한국주식 전용)      ← 신규
- **종합 인사이트** (모든 팩터 통합 추천 + 리스크)         ← 신규
```

환경변수 안내 추가:

```markdown
**선택 환경변수:**
- `OPENDART_API_KEY`: 한국주식 공시 조회 (없으면 공시 섹션 생략)
- `KIS_APP_KEY` / `KIS_APP_SECRET`: 수급 동향 조회 (없으면 수급 섹션 생략)
```

- [ ] **Step 4: `CLAUDE.md` 아키텍처 섹션에 신규 모듈 추가**

Key modules 목록에 추가:

```
- `src/tools/disclosure.py` — SEC EDGAR + DART 통합 공시 페처
- `src/tools/flow.py` — KIS API 수급 데이터 (외인/기관 순매수)
```

- [ ] **Step 5: 최종 테스트 실행**

```
uv run pytest -v
```
예상: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add README.md docs/CLI_USAGE.md CLAUDE.md
git commit -m "docs: update README, CLI_USAGE, CLAUDE.md for disclosure and flow features"
```

---

## 셀프 리뷰

### 1. 스펙 커버리지

| 스펙 요구사항 | 구현 태스크 |
|--------------|------------|
| SEC EDGAR: 10-Q, 8-K, 최근 3개월, 최대 5건 | Task 2: `SECDisclosureFetcher` |
| CIK 조회 (`company_tickers.json`), 6시간 캐시 | Task 2: `_get_cik()` + `_load_cache()` |
| DART: corp_code 조회 (OpenDART) | Task 3: `DARTDisclosureFetcher._get_corp_code()` |
| DART: 키워드 필터링 + 중요도 스코어링 | Task 3: `_score_dart_report()` |
| DART: score ≥ 1.0 임계값, 최대 5건 | Task 3: `_DART_SCORE_THRESHOLD`, `_DART_MAX_RESULTS` |
| KIS 수급 데이터: 외인/기관 10일 조회 | Task 5: `FlowTool` (`days=10`) |
| 1일·5일·10일 구간별 방향 판단 | Task 5: `foreign_direction_1d/5d/10d`, `institution_direction_1d/5d/10d` |
| 10일 중 순매수 일수 | Task 5: `foreign_buy_days`, `institution_buy_days` |
| 파이프라인 병렬 실행 | Task 6: `asyncio.gather(*optional_coros)` |
| LLM 프롬프트에 공시 + 수급 컨텍스트 | Task 7: `generate_integrated_analysis()` |
| 출력 섹션: 공시 분석 | Task 8: `format_deep_dive_output()` |
| 출력 섹션: 수급 동향 | Task 8: `format_deep_dive_output()` |
| 출력 섹션: 종합 인사이트 | Task 8: `format_deep_dive_output()` |
| `OPENDART_API_KEY` 환경변수 | Task 9: `run_deep_dive()` |
| 문서화 | Task 10 |

모든 요구사항 커버 ✅

### 2. 플레이스홀더 검사

TODO, TBD, "적절한 에러 처리 추가" 패턴 없음. 모든 스텝에 실제 코드 포함. ✅

### 3. 타입 일관성

- `DisclosureItem`: Task 1 정의 → Task 4, 6, 7, 8에서 올바르게 임포트
- `InvestorFlow` / `InvestorFlowEntry`: Task 5 정의 → Task 6, 7, 8에서 사용
- `IntegratedAnalysisInput` / `IntegratedAnalysisOutput`: Task 7 정의 → Task 6 (`deep_dive.py`), Task 7 (`analyzer.py`)에서 임포트
- `_format_flow_for_llm()`: Task 6 (`deep_dive.py`)에서 정의 및 사용
- `DisclosureTool.execute()` → `ToolResult.data`는 `list[DisclosureItem]` → Task 6, 8에서 올바르게 사용
- 전체 일관성 확인 ✅
