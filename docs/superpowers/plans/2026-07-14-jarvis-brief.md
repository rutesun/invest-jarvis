# jarvis brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로컬 `playbook.yaml`(holdings+watchlist)을 입력으로 종목별 액션 신호·우선순위 큐·진입 임박 후보를 마크다운으로 출력하는 온디맨드 CLI `jarvis brief`를 만든다.

**Architecture:** 신규 `BriefPipeline`이 기존 부품(TechnicalAnalysisTool, PlaybookEngine, MacroTool, NewsTool, DisclosureTool, FlowTool)을 조립한다. 액션·순위·근거는 규칙이 결정적으로 확정(버킷 랭킹)하고, LLM은 배치 1콜로 슬롯 문장화만 담당(실패 시 규칙 원문 fallback). 선행으로 exit_rules의 SMA 컬럼 계약 버그(기존 `analyze`에도 영향)를 수정한다.

**Tech Stack:** Python 3.12+, uv, typer, rich, pydantic, langchain (기존 `src/llm/` 패턴), pytest + AsyncMock

**Spec:** `docs/superpowers/specs/2026-07-14-jarvis-brief-design.md` (결정 이력 D1~D10 포함)

## Global Constraints

- Python >= 3.12, 패키지 관리는 항상 `uv` (`uv run pytest`, `uv sync`)
- 레이어드 아키텍처 준수: Providers → Tools → Pipelines → CLI. 역방향 의존 금지
- 기존 파이프라인(deep_dive, ticker_report, daily_report, screener) 무변경. TickerReportPipeline 유지
- 보유/워치 판정은 **`PlaybookEngine.evaluate()` 단일 진입점** — `evaluate_exit` 직접 호출 금지
- 랭킹: **버킷 순서 절대 우선**, 가산점(스탑 근접 +30, 급변 +20)은 동버킷 내 정렬 전용
- 진입 임박 = gate 미통과 && 필수 게이트 4개(A·B·C·E) 중 정확히 3개 `met=True`
- 뉴스·공시·수급은 점수에 미반영(표기 전용). LLM 실패 시에도 브리핑은 항상 완성
- 개별 종목·데이터소스 실패는 전체를 막지 않음(`logger.warning` + 항목 생략). 단 playbook.yaml 스키마 오류는 즉시 예외
- 커밋 메시지는 기존 컨벤션(`feat:`/`fix:`/`docs:`/`refactor:`) + 마지막 줄 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- 작업 브랜치: `feature/jarvis-brief` (워크트리 `.claude/worktrees/jarvis-brief`)

---

### Task 1: exit_rules SMA 컬럼 계약 버그 수정 (선행)

**배경:** `exit_rules.py`는 `"SMA20"` 형식 컬럼을 찾지만 `IndicatorCalculator`(src/tools/technical/indicators.py:24-29)는 `"SMA_20"` 형식을 생성한다. 실경로(`technical_result.raw_dataframe`)에서는 SMA_SHORT/SMA_LONG 매도신호와 trailing_stop이 조용히 누락된다(기존 `analyze` 버그). 기존 단위테스트는 자체 픽스처를 `"SMA20"` 이름으로 만들어 통과해 왔다.

**Files:**
- Modify: `src/tools/playbook/exit_rules.py:161-167` (`_get_ma`)
- Test: `tests/tools/playbook/test_exit_rules.py`

**Interfaces:**
- Consumes: 없음 (독립 버그픽스)
- Produces: `evaluate_exit(df, ...)`가 `SMA20`·`SMA_20` 양쪽 컬럼명에서 동작 (시그니처 무변경)

- [ ] **Step 1: 실경로 컬럼명(SMA_50 형식)으로 실패하는 테스트 작성**

`tests/tools/playbook/test_exit_rules.py` 끝에 추가:

```python
def test_sma_signals_fire_with_underscore_columns():
    """indicators.py 실제 컬럼명(SMA_50 형식)으로도 SMA 신호가 발화해야 한다 (계약 회귀)."""
    df = pd.DataFrame({"Close": [100.0] * 60})
    df.loc[df.index[-1], "Close"] = 80.0
    df["SMA_20"] = 90.0
    df["SMA_50"] = 85.0
    df["SMA_150"] = 95.0
    df["SMA_200"] = 96.0

    verdict = evaluate_exit(
        df=df, snapshot=None, relative_strength=None, accumulation=None, holding=None
    )

    codes = {s.code for s in verdict.signals}
    assert "SMA_SHORT" in codes
    assert "SMA_LONG" in codes
    assert verdict.trailing_stop == 85.0
    assert verdict.action == "liquidate"  # strong 1개(SMA_LONG) → 청산
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/tools/playbook/test_exit_rules.py::test_sma_signals_fire_with_underscore_columns -v`
Expected: FAIL — `codes`가 비어 있어 `assert "SMA_SHORT" in codes` 실패

- [ ] **Step 3: `_get_ma`를 양쪽 컬럼명 허용으로 수정**

`src/tools/playbook/exit_rules.py`의 `_get_ma` 교체:

```python
def _get_ma(df: pd.DataFrame, col: str, last) -> float | None:
    """DataFrame 마지막 행에서 이동평균 값 추출.

    'SMA50'(레거시 픽스처)·'SMA_50'(IndicatorCalculator 실제 출력) 양식 모두 허용.
    """
    for name in (col, col.replace("SMA", "SMA_", 1)):
        if name in df.columns:
            val = last.get(name)
            if val is not None and not pd.isna(val):
                return float(val)
    return None
```

- [ ] **Step 4: 신규 + 기존 테스트 전부 통과 확인**

Run: `uv run pytest tests/tools/playbook/test_exit_rules.py -v`
Expected: 전부 PASS (기존 `SMA20` 픽스처 테스트도 첫 번째 이름 매칭으로 통과)

- [ ] **Step 5: worklog에 [Bug] 엔트리 기록**

`docs/worklog/jarvis-brief.md` 끝에 append (시각은 `date '+%Y-%m-%d %H:%M'` 실행값으로 치환):

```markdown
## (YYYY-MM-DD HH:MM) [Bug] exit_rules SMA 컬럼 계약 불일치 수정
- 증상: analyze 보유 종목 매도판정에서 SMA_SHORT/SMA_LONG 신호·trailing_stop이 발화하지 않음
- 근원(root cause): exit_rules는 "SMA20" 컬럼을 찾는데 IndicatorCalculator는 "SMA_20"을 생성. 단위테스트가 자체 픽스처("SMA20")로 계약 불일치를 은폐
- 수정: _get_ma가 양쪽 컬럼명을 순서대로 조회. 실경로 컬럼명 회귀 테스트 추가
- 재발 방지 / 배운 것: 부품 간 DataFrame 컬럼 계약은 생산자 실제 출력으로 테스트해야 함 (CLAUDE.md 골든 테스트 원칙의 단위테스트 버전)
```

- [ ] **Step 6: Commit**

```bash
git add src/tools/playbook/exit_rules.py tests/tools/playbook/test_exit_rules.py docs/worklog/jarvis-brief.md
git commit -m "fix: exit_rules가 IndicatorCalculator 실제 SMA 컬럼명(SMA_50)을 인식하도록 수정

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: playbook.yaml watchlist 섹션 + 로더 확장

**Files:**
- Modify: `src/tools/playbook/holdings.py` (전체 93줄 — WatchEntry 추가, load_holdings 확장)
- Test: `tests/tools/playbook/test_holdings.py`

**Interfaces:**
- Consumes: `is_korean_ticker(ticker: str) -> bool` (src/tools/disclosure.py:28, 이미 import됨)
- Produces (Task 6이 사용):
  - `WatchEntry` dataclass: `ticker: str`, `note: str | None`, `currency: str`
  - `HoldingsConfig.watchlist: list[WatchEntry]` (기본 빈 리스트)
  - `load_holdings()` — watchlist 파싱, holdings 우선 중복 제거, 스키마 오류 시 `ValueError("playbook.yaml watchlist[i]: ...")`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/tools/playbook/test_holdings.py` 끝에 추가 (기존 테스트들과 같은 `tmp_path` 패턴):

```python
def test_load_watchlist_basic(tmp_path):
    p = tmp_path / "playbook.yaml"
    p.write_text(
        """
watchlist:
  - ticker: NVDA
    note: "AI 반도체"
  - ticker: "035420"
""",
        encoding="utf-8",
    )
    config = load_holdings(p)
    assert len(config.watchlist) == 2
    assert config.watchlist[0].ticker == "NVDA"
    assert config.watchlist[0].note == "AI 반도체"
    assert config.watchlist[0].currency == "USD"
    assert config.watchlist[1].note is None
    assert config.watchlist[1].currency == "KRW"


def test_load_watchlist_absent_returns_empty(tmp_path):
    p = tmp_path / "playbook.yaml"
    p.write_text("holdings: []\n", encoding="utf-8")
    assert load_holdings(p).watchlist == []


def test_watchlist_dedupe_holdings_first(tmp_path, caplog):
    """holdings에 있는 티커는 watchlist에서 무시 (보유 우선)."""
    p = tmp_path / "playbook.yaml"
    p.write_text(
        """
holdings:
  - ticker: NVDA
    quantity: 5
    avg_price: 150.0
watchlist:
  - ticker: nvda
  - ticker: AAPL
""",
        encoding="utf-8",
    )
    config = load_holdings(p)
    assert [w.ticker for w in config.watchlist] == ["AAPL"]


def test_watchlist_dedupe_within_watchlist(tmp_path):
    p = tmp_path / "playbook.yaml"
    p.write_text(
        """
watchlist:
  - ticker: AAPL
  - ticker: aapl
""",
        encoding="utf-8",
    )
    config = load_holdings(p)
    assert len(config.watchlist) == 1


def test_watchlist_missing_ticker_raises(tmp_path):
    p = tmp_path / "playbook.yaml"
    p.write_text(
        """
watchlist:
  - note: "티커 없음"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"watchlist\[0\]"):
        load_holdings(p)


def test_holdings_missing_field_raises_with_index(tmp_path):
    p = tmp_path / "playbook.yaml"
    p.write_text(
        """
holdings:
  - ticker: AAPL
    quantity: 5
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"holdings\[0\]"):
        load_holdings(p)
```

파일 상단에 `import pytest`가 없으면 추가.

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/tools/playbook/test_holdings.py -v -k "watchlist or missing_field"`
Expected: FAIL — `HoldingsConfig`에 `watchlist` 속성 없음 / raw `KeyError`

- [ ] **Step 3: holdings.py 구현**

`src/tools/playbook/holdings.py` 전체를 다음으로 교체:

```python
"""playbook.yaml 보유 종목·워치리스트 및 계좌 설정 로더 (Plan 8 + brief)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.tools.disclosure import is_korean_ticker

logger = logging.getLogger(__name__)


@dataclass
class HoldingEntry:
    """보유 종목 단일 항목."""

    ticker: str
    quantity: int
    avg_price: float
    stop_price: float | None
    currency: str  # "KRW" | "USD"


@dataclass
class WatchEntry:
    """워치리스트 단일 항목 (관심 = 티커만 필수)."""

    ticker: str
    note: str | None
    currency: str  # "KRW" | "USD"


@dataclass
class HoldingsConfig:
    """playbook.yaml 전체 설정."""

    krw_capital: float | None
    krw_risk_pct: float | None
    usd_capital: float | None
    usd_risk_pct: float | None
    holdings: list[HoldingEntry] = field(default_factory=list)
    watchlist: list[WatchEntry] = field(default_factory=list)

    def find(self, ticker: str) -> HoldingEntry | None:
        """대소문자 무시 티커 검색. 없으면 None."""
        upper = ticker.upper()
        return next((h for h in self.holdings if h.ticker.upper() == upper), None)

    def get_account_for(self, ticker: str) -> tuple[float | None, float | None]:
        """티커 통화에 맞는 (capital, risk_pct) 반환. 설정 없으면 (None, None)."""
        if is_korean_ticker(ticker):
            return self.krw_capital, self.krw_risk_pct
        return self.usd_capital, self.usd_risk_pct


def load_holdings(path: str | Path = "playbook.yaml") -> HoldingsConfig:
    """playbook.yaml 로드. 파일 없으면 빈 설정 반환. 스키마 오류는 항목 인덱스와 함께 즉시 예외."""
    p = Path(path)
    if not p.exists():
        return HoldingsConfig(
            krw_capital=None,
            krw_risk_pct=None,
            usd_capital=None,
            usd_risk_pct=None,
        )

    with p.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    account = data.get("account") or {}
    krw = account.get("krw") or {}
    usd = account.get("usd") or {}

    holdings = _parse_holdings(data.get("holdings") or [])
    watchlist = _parse_watchlist(data.get("watchlist") or [], holdings)

    return HoldingsConfig(
        krw_capital=float(krw["capital"]) if krw.get("capital") is not None else None,
        krw_risk_pct=float(krw["risk_per_trade_pct"])
        if krw.get("risk_per_trade_pct") is not None
        else None,
        usd_capital=float(usd["capital"]) if usd.get("capital") is not None else None,
        usd_risk_pct=float(usd["risk_per_trade_pct"])
        if usd.get("risk_per_trade_pct") is not None
        else None,
        holdings=holdings,
        watchlist=watchlist,
    )


def _parse_holdings(raw: list) -> list[HoldingEntry]:
    holdings: list[HoldingEntry] = []
    for i, item in enumerate(raw):
        try:
            ticker = str(item["ticker"])
            currency = "KRW" if is_korean_ticker(ticker) else "USD"
            holdings.append(
                HoldingEntry(
                    ticker=ticker,
                    quantity=int(item["quantity"]),
                    avg_price=float(item["avg_price"]),
                    stop_price=float(item["stop_price"])
                    if item.get("stop_price") is not None
                    else None,
                    currency=currency,
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"playbook.yaml holdings[{i}] 파싱 실패: {e!r}") from e
    return holdings


def _parse_watchlist(raw: list, holdings: list[HoldingEntry]) -> list[WatchEntry]:
    holding_tickers = {h.ticker.upper() for h in holdings}
    watchlist: list[WatchEntry] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or "ticker" not in item:
            raise ValueError(f"playbook.yaml watchlist[{i}]: 'ticker' 필드가 필요합니다")
        ticker = str(item["ticker"])
        upper = ticker.upper()
        if upper in holding_tickers:
            logger.warning(
                "watchlist 티커 %s는 holdings에 이미 존재 — 보유 우선, 워치에서 무시", ticker
            )
            continue
        if upper in seen:
            logger.warning("watchlist 티커 %s 중복 — 첫 항목만 사용", ticker)
            continue
        seen.add(upper)
        note = item.get("note")
        watchlist.append(
            WatchEntry(
                ticker=ticker,
                note=str(note) if note is not None else None,
                currency="KRW" if is_korean_ticker(ticker) else "USD",
            )
        )
    return watchlist
```

- [ ] **Step 4: 신규 + 기존 테스트 전부 통과 확인**

Run: `uv run pytest tests/tools/playbook/test_holdings.py -v`
Expected: 전부 PASS (기존 13개 테스트 포함 — 시그니처·기존 동작 무변경)

- [ ] **Step 5: Commit**

```bash
git add src/tools/playbook/holdings.py tests/tools/playbook/test_holdings.py
git commit -m "feat: playbook.yaml watchlist 섹션 파싱 추가 (보유 우선 dedupe, 명시적 스키마 에러)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: brief 도메인 모델 + 랭킹 순수 함수

**Files:**
- Create: `src/tools/brief/__init__.py` (빈 파일)
- Create: `src/tools/brief/models.py`
- Create: `src/tools/brief/scoring.py`
- Test: `tests/tools/brief/__init__.py` (빈 파일), `tests/tools/brief/test_scoring.py`

**Interfaces:**
- Consumes: `GateResult`, `GateCheck`, `ExitVerdict`, `PlaybookVerdict` (src/tools/playbook/models.py), `HoldingEntry` (holdings.py)
- Produces (Task 5·6이 사용):
  - `BriefItem` dataclass — 아래 필드 전부
  - `classify_watch(gate: GateResult) -> tuple[str, str | None]` — ("eligible"|"imminent"|"rejected", 임박 시 남은 조건 문자열)
  - `bucket_for(kind: str, action: str, has_warn_signals: bool = False) -> int`
  - `is_stop_proximate(price: float | None, stop_price: float | None) -> bool`
  - `surge_reason(kind: str, change_pct: float | None) -> str | None`
  - `rank(items: list[BriefItem]) -> list[BriefItem]`
  - 상수: `BUCKET_LABELS: dict[int, str]`, `BONUS_STOP_PROXIMITY = 30`, `BONUS_SURGE = 20`

- [ ] **Step 1: models.py 작성** (테스트 대상인 scoring이 의존하므로 먼저)

`src/tools/brief/models.py`:

```python
"""brief 도메인 모델 — 종목별 판정 결과 집계 단위."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.tools.disclosure import DisclosureItem
from src.tools.flow import InvestorFlow
from src.tools.news import NewsArticle
from src.tools.playbook.holdings import HoldingEntry
from src.tools.playbook.models import PlaybookVerdict

# 버킷 순서 = 절대 우선순위 (낮을수록 상단). 스펙 §5.2
BUCKET_LIQUIDATE = 1  # 청산 — "놓치면 손실"
BUCKET_BUY_ELIGIBLE = 2  # 매수 적격 — "놓치면 기회"
BUCKET_REDUCE = 3  # 비중축소
BUCKET_IMMINENT = 4  # 진입 임박
BUCKET_HOLD_WARN = 5  # 보유(약신호 있음)
BUCKET_REJECTED = 6  # 거부(워치)
BUCKET_HOLD_OK = 7  # 보유(이상 없음) / 데이터 실패

BUCKET_LABELS: dict[int, str] = {
    BUCKET_LIQUIDATE: "청산",
    BUCKET_BUY_ELIGIBLE: "매수 적격",
    BUCKET_REDUCE: "비중축소",
    BUCKET_IMMINENT: "진입 임박",
    BUCKET_HOLD_WARN: "보유(약신호)",
    BUCKET_REJECTED: "거부",
    BUCKET_HOLD_OK: "보유",
}


@dataclass
class BriefItem:
    """종목 하나의 브리핑 항목 — 규칙 판정 결과 + 근거 데이터 집계."""

    ticker: str
    kind: str  # "holding" | "watch"
    action: str  # "liquidate"|"reduce"|"hold"|"eligible"|"imminent"|"rejected"|"error"
    bucket: int
    bonus: int = 0
    markers: list[str] = field(default_factory=list)  # "스탑 근접", "급변: ..." 등
    note: str | None = None  # watchlist note
    holding: HoldingEntry | None = None
    verdict: PlaybookVerdict | None = None
    news: list[NewsArticle] = field(default_factory=list)
    disclosures: list[DisclosureItem] = field(default_factory=list)
    flow: InvestorFlow | None = None
    price: float | None = None
    change_pct: float | None = None
    remaining_condition: str | None = None  # 임박 시 미충족 게이트 1개
    narrative: Any | None = None  # TickerNarrative (Task 4) — 순환 import 방지로 Any
    error: str | None = None
```

- [ ] **Step 2: 실패하는 scoring 테스트 작성**

`tests/tools/brief/test_scoring.py`:

```python
"""brief 랭킹/판정 순수 함수 테스트. I/O 없음."""

from src.tools.brief.models import (
    BUCKET_BUY_ELIGIBLE,
    BUCKET_HOLD_OK,
    BUCKET_HOLD_WARN,
    BUCKET_IMMINENT,
    BUCKET_LIQUIDATE,
    BUCKET_REDUCE,
    BUCKET_REJECTED,
    BriefItem,
)
from src.tools.brief.scoring import (
    BONUS_STOP_PROXIMITY,
    BONUS_SURGE,
    bucket_for,
    classify_watch,
    is_stop_proximate,
    rank,
    surge_reason,
)
from src.tools.playbook.models import GateCheck, GateResult


def _gate(met_flags: dict[str, bool | None], passed: bool = False) -> GateResult:
    checklist = [
        GateCheck(name=n, required=True, met=met_flags[n], reason=f"{n} 사유")
        for n in ("A", "B", "C", "E")
    ]
    return GateResult(passed=passed, checklist=checklist, quality_grade=None, veto_reason=None)


# ── classify_watch: 임박 = 필수 4중 정확히 3 충족 ──────────────────────────


def test_classify_watch_eligible():
    gate = _gate({"A": True, "B": True, "C": True, "E": True}, passed=True)
    assert classify_watch(gate) == ("eligible", None)


def test_classify_watch_imminent_3_of_4():
    gate = _gate({"A": True, "B": True, "C": True, "E": False})
    action, remaining = classify_watch(gate)
    assert action == "imminent"
    assert remaining == "E: E 사유"


def test_classify_watch_rejected_2_of_4():
    gate = _gate({"A": True, "B": True, "C": False, "E": False})
    assert classify_watch(gate) == ("rejected", None)


def test_classify_watch_none_counts_as_unmet():
    """met=None(데이터 없음)은 미충족으로 취급 — 3 True + 1 None = 임박."""
    gate = _gate({"A": True, "B": True, "C": True, "E": None})
    action, remaining = classify_watch(gate)
    assert action == "imminent"
    assert remaining.startswith("E:")


# ── bucket_for ──────────────────────────────────────────────────────────────


def test_bucket_mapping():
    assert bucket_for("holding", "liquidate") == BUCKET_LIQUIDATE
    assert bucket_for("watch", "eligible") == BUCKET_BUY_ELIGIBLE
    assert bucket_for("holding", "reduce") == BUCKET_REDUCE
    assert bucket_for("watch", "imminent") == BUCKET_IMMINENT
    assert bucket_for("holding", "hold", has_warn_signals=True) == BUCKET_HOLD_WARN
    assert bucket_for("watch", "rejected") == BUCKET_REJECTED
    assert bucket_for("holding", "hold", has_warn_signals=False) == BUCKET_HOLD_OK
    assert bucket_for("holding", "error") == BUCKET_HOLD_OK
    assert bucket_for("watch", "error") == BUCKET_HOLD_OK


# ── 가산 마커 ───────────────────────────────────────────────────────────────


def test_stop_proximate_within_3pct():
    assert is_stop_proximate(price=102.9, stop_price=100.0) is True
    assert is_stop_proximate(price=103.1, stop_price=100.0) is False
    assert is_stop_proximate(price=99.0, stop_price=100.0) is True  # 이미 이탈 → 근접
    assert is_stop_proximate(price=None, stop_price=100.0) is False
    assert is_stop_proximate(price=100.0, stop_price=None) is False


def test_surge_reason_direction():
    assert surge_reason("holding", -5.2) == "급변: 보유 급락"
    assert surge_reason("holding", 6.0) == "급변: 보유 급등"
    assert surge_reason("watch", 5.5) == "급변: 워치 상승 돌파"
    assert surge_reason("watch", -7.0) == "급변: 워치 급락"
    assert surge_reason("holding", 4.9) is None
    assert surge_reason("holding", None) is None


# ── rank: 버킷 절대 우선, 가산점은 동버킷 내 정렬 전용 ──────────────────────


def _item(ticker: str, bucket: int, bonus: int = 0) -> BriefItem:
    return BriefItem(ticker=ticker, kind="holding", action="hold", bucket=bucket, bonus=bonus)


def test_rank_bucket_absolute_priority():
    """축소(버킷3)+가산 110점이어도 청산(버킷1)을 역전하지 못한다."""
    reduce_boosted = _item("A", BUCKET_REDUCE, bonus=BONUS_STOP_PROXIMITY + BONUS_SURGE)
    liquidate_plain = _item("B", BUCKET_LIQUIDATE, bonus=0)
    ranked = rank([reduce_boosted, liquidate_plain])
    assert [i.ticker for i in ranked] == ["B", "A"]


def test_rank_bonus_breaks_tie_within_bucket():
    a = _item("A", BUCKET_HOLD_WARN, bonus=0)
    b = _item("B", BUCKET_HOLD_WARN, bonus=BONUS_STOP_PROXIMITY)
    ranked = rank([a, b])
    assert [i.ticker for i in ranked] == ["B", "A"]


def test_rank_is_stable_for_equal_keys():
    a = _item("A", BUCKET_HOLD_OK)
    b = _item("B", BUCKET_HOLD_OK)
    assert [i.ticker for i in rank([a, b])] == ["A", "B"]
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/tools/brief/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: src.tools.brief.scoring`

- [ ] **Step 4: scoring.py 구현**

`src/tools/brief/scoring.py`:

```python
"""brief 랭킹/판정 규칙 — 순수 함수, I/O 없음.

버킷 순서가 절대 우선이고, 가산점(스탑 근접·급변)은 동버킷 내 정렬에만 쓴다.
가산점이 버킷을 역전하면 "축소+스탑근접 > 청산" 같은 왜곡이 생기기 때문 (스펙 §5.2).
"""

from __future__ import annotations

from src.tools.brief.models import (
    BUCKET_BUY_ELIGIBLE,
    BUCKET_HOLD_OK,
    BUCKET_HOLD_WARN,
    BUCKET_IMMINENT,
    BUCKET_LIQUIDATE,
    BUCKET_REDUCE,
    BUCKET_REJECTED,
    BriefItem,
)
from src.tools.playbook.models import GateResult

BONUS_STOP_PROXIMITY = 30
BONUS_SURGE = 20
STOP_PROXIMITY_RATIO = 1.03  # 현재가 <= 스탑 × 1.03 → 근접(이탈 포함)
SURGE_PCT = 5.0  # 당일 등락 ±5% 이상


def classify_watch(gate: GateResult) -> tuple[str, str | None]:
    """워치 종목 판정. 임박 = 필수 게이트 4개 중 정확히 3개 met=True.

    Stage2 개수만 보면 시장 하락·RS 약세를 무시하므로 checklist 기반으로 판정 (스펙 D9).
    """
    if gate.passed:
        return "eligible", None
    required = [c for c in gate.checklist if c.required]
    met_count = sum(1 for c in required if c.met is True)
    if len(required) == 4 and met_count == 3:
        failed = next(c for c in required if c.met is not True)
        return "imminent", f"{failed.name}: {failed.reason}"
    return "rejected", None


def bucket_for(kind: str, action: str, has_warn_signals: bool = False) -> int:
    """(kind, action) → 버킷 번호."""
    if action == "liquidate":
        return BUCKET_LIQUIDATE
    if action == "eligible":
        return BUCKET_BUY_ELIGIBLE
    if action == "reduce":
        return BUCKET_REDUCE
    if action == "imminent":
        return BUCKET_IMMINENT
    if action == "rejected":
        return BUCKET_REJECTED
    if action == "hold" and has_warn_signals:
        return BUCKET_HOLD_WARN
    return BUCKET_HOLD_OK  # hold(무신호) / error


def is_stop_proximate(price: float | None, stop_price: float | None) -> bool:
    """현재가가 스탑 대비 3% 이내(이탈 포함)면 True."""
    if price is None or stop_price is None or stop_price <= 0:
        return False
    return price <= stop_price * STOP_PROXIMITY_RATIO


def surge_reason(kind: str, change_pct: float | None) -> str | None:
    """당일 ±5% 이상 급변 시 방향별 사유. 아니면 None."""
    if change_pct is None or abs(change_pct) < SURGE_PCT:
        return None
    if kind == "holding":
        return "급변: 보유 급등" if change_pct > 0 else "급변: 보유 급락"
    return "급변: 워치 상승 돌파" if change_pct > 0 else "급변: 워치 급락"


def rank(items: list[BriefItem]) -> list[BriefItem]:
    """버킷 오름차순 → 가산점 내림차순. 안정 정렬."""
    return sorted(items, key=lambda i: (i.bucket, -i.bonus))
```

`src/tools/brief/__init__.py`, `tests/tools/brief/__init__.py`는 빈 파일로 생성.

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/tools/brief/test_scoring.py -v`
Expected: 전부 PASS

- [ ] **Step 6: Commit**

```bash
git add src/tools/brief/ tests/tools/brief/
git commit -m "feat: brief 버킷 랭킹·임박 판정 순수 함수 추가

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: LLM 배치 문장화 (generate_brief_narratives)

**Files:**
- Modify: `src/llm/models.py` (끝에 모델 2개 추가)
- Modify: `src/llm/analyzer.py` (끝에 함수 1개 추가)
- Test: `tests/llm/test_brief_narratives.py`

**Interfaces:**
- Consumes: 기존 analyzer 패턴 — `ChatPromptTemplate` → `llm.with_structured_output(Model)` → `await chain.ainvoke({...})`
- Produces (Task 6이 사용):
  - `TickerNarrative`: `ticker: str`, `technical_note: str`, `flow_note: str | None`, `news_note: str | None`, `next_check: str`
  - `BriefNarrativesOutput`: `narratives: list[TickerNarrative]`
  - `async def generate_brief_narratives(facts_json: str, llm: BaseChatModel) -> BriefNarrativesOutput`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/llm/test_brief_narratives.py`:

```python
"""generate_brief_narratives — LLM 목으로 프롬프트 조립·구조화 출력 검증."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.llm.analyzer import generate_brief_narratives
from src.llm.models import BriefNarrativesOutput, TickerNarrative


@pytest.mark.asyncio
async def test_generate_brief_narratives_returns_structured_output():
    expected = BriefNarrativesOutput(
        narratives=[
            TickerNarrative(
                ticker="NVDA",
                technical_note="Stage2 7/7 충족, VCP 돌파 확인.",
                flow_note=None,
                news_note="신규 수주 발표가 돌파를 뒷받침.",
                next_check="진입 후 stop 152.0 관리.",
            )
        ]
    )
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value=expected)
    mock_llm = MagicMock()
    # prompt | llm.with_structured_output(...) 체인의 최종 ainvoke만 목 처리
    mock_llm.with_structured_output.return_value = mock_chain
    # ChatPromptTemplate | mock 은 RunnableSequence를 만들므로, __or__ 결과를 직접 목:
    mock_llm.with_structured_output.return_value.__ror__ = MagicMock(return_value=mock_chain)

    result = await generate_brief_narratives('{"items": []}', llm=mock_llm)

    assert isinstance(result, BriefNarrativesOutput)
    assert result.narratives[0].ticker == "NVDA"
    mock_llm.with_structured_output.assert_called_once()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/llm/test_brief_narratives.py -v`
Expected: FAIL — `ImportError: generate_brief_narratives`

- [ ] **Step 3: 모델 + 함수 구현**

`src/llm/models.py` 끝에 추가:

```python
class TickerNarrative(BaseModel):
    """brief 종목별 서술 슬롯 — 규칙 판정 사실의 문장화만 담당."""

    ticker: str = Field(description="입력 사실 JSON의 ticker 그대로")
    technical_note: str = Field(description="기술적 근거 1-2문장 (제공된 사실만 사용)")
    flow_note: str | None = Field(default=None, description="수급 데이터가 있으면 1문장")
    news_note: str | None = Field(default=None, description="뉴스가 있으면 해석 1문장")
    next_check: str = Field(description="다음 확인 지점 1문장")


class BriefNarrativesOutput(BaseModel):
    """brief LLM 배치 1콜 출력 — 전 종목 서술 목록."""

    narratives: list[TickerNarrative]
```

`src/llm/analyzer.py` 끝에 추가 (파일 상단 import에 `BriefNarrativesOutput` 추가):

```python
async def generate_brief_narratives(
    facts_json: str,
    llm: BaseChatModel,
) -> BriefNarrativesOutput:
    """전 종목 규칙 판정 사실(JSON)을 배치 1콜로 문장화한다.

    액션·순위·근거는 이미 규칙이 확정 — LLM은 서술만 담당하며,
    사실에 없는 수치·사건을 만들면 안 된다 (스펙 §6.1).
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "당신은 한국어 투자 브리핑 작성자다. 제공된 '규칙 판정 사실'만 사용해 "
                "각 종목의 서술 슬롯을 채운다. 사실에 없는 수치·사건·전망을 만들지 마라. "
                "모든 종목에 대해 하나씩 narrative를 반환하라.",
            ),
            (
                "user",
                "다음은 종목별 규칙 판정 결과 JSON이다:\n\n{facts_json}\n\n"
                "각 종목에 대해 technical_note(기술적 근거 1-2문장), "
                "flow_note(수급 사실이 있으면 1문장, 없으면 null), "
                "news_note(뉴스가 있으면 해석 1문장, 없으면 null), "
                "next_check(다음 확인 지점 1문장)를 작성하라.",
            ),
        ]
    )
    chain = prompt | llm.with_structured_output(BriefNarrativesOutput)
    return await chain.ainvoke({"facts_json": facts_json})
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/llm/test_brief_narratives.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/llm/models.py src/llm/analyzer.py tests/llm/test_brief_narratives.py
git commit -m "feat: brief LLM 배치 문장화 함수 추가 (구조화 슬롯 출력)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: 마크다운 렌더러

**Files:**
- Create: `src/tools/brief/render.py`
- Test: `tests/tools/brief/test_render.py`

**Interfaces:**
- Consumes: `BriefItem`, `BUCKET_LABELS` (Task 3), `TickerNarrative` (Task 4), `TickerMacroSnapshot` (src/tools/macro.py)
- Produces (Task 6·7이 사용): `def render_markdown(date: datetime, macro: TickerMacroSnapshot | None, items: list[BriefItem], top_n: int = 3) -> str` — `items`는 이미 rank() 정렬된 상태를 가정

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/tools/brief/test_render.py`:

```python
"""render_markdown — 규칙 원문 fallback 포함 마크다운 조립 검증."""

from datetime import datetime

from src.tools.brief.models import (
    BUCKET_BUY_ELIGIBLE,
    BUCKET_HOLD_OK,
    BUCKET_REDUCE,
    BriefItem,
)
from src.tools.brief.render import render_markdown


def _items():
    return [
        BriefItem(
            ticker="NVDA", kind="watch", action="eligible",
            bucket=BUCKET_BUY_ELIGIBLE, price=165.2, change_pct=1.2,
        ),
        BriefItem(
            ticker="005930", kind="holding", action="reduce",
            bucket=BUCKET_REDUCE, price=71200.0, change_pct=-1.1,
            markers=["스탑 근접"],
        ),
        BriefItem(
            ticker="AAPL", kind="holding", action="hold",
            bucket=BUCKET_HOLD_OK, price=210.0, change_pct=0.3,
        ),
    ]


def test_render_contains_sections_and_top3():
    md = render_markdown(datetime(2026, 7, 14), macro=None, items=_items())
    assert "# Daily Brief — 2026-07-14" in md
    assert "## ⚡ 오늘의 액션" in md
    assert "## 보유" in md
    assert "## 워치리스트" in md
    # Top-3에 랭킹 순서대로 (입력이 이미 정렬됨)
    action_section = md.split("## ⚡ 오늘의 액션")[1].split("## 보유")[0]
    assert action_section.index("NVDA") < action_section.index("005930")


def test_render_all_items_present_no_omission():
    """전 종목 누락 없음 — 스펙 D5."""
    md = render_markdown(datetime(2026, 7, 14), macro=None, items=_items())
    for ticker in ("NVDA", "005930", "AAPL"):
        assert md.count(ticker) >= 2  # Top-N 또는 상세 섹션 + 헤더


def test_render_marker_shown():
    md = render_markdown(datetime(2026, 7, 14), macro=None, items=_items())
    assert "스탑 근접" in md


def test_render_error_item():
    items = [
        BriefItem(
            ticker="FAIL", kind="watch", action="error",
            bucket=BUCKET_HOLD_OK, error="기술분석 실패: timeout",
        )
    ]
    md = render_markdown(datetime(2026, 7, 14), macro=None, items=items)
    assert "데이터 조회 실패" in md
    assert "timeout" in md


def test_render_empty_items():
    md = render_markdown(datetime(2026, 7, 14), macro=None, items=[])
    assert "설정된 종목 없음" in md
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/tools/brief/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: src.tools.brief.render`

- [ ] **Step 3: render.py 구현**

`src/tools/brief/render.py`:

```python
"""brief 마크다운 렌더러 — 순수 함수.

LLM narrative가 없으면(실패/미사용) 규칙 원문으로 슬롯을 채운다 (스펙 §6.1 fallback).
데이터 없는 슬롯은 항목 자체를 생략한다 (스펙 §6.2).
"""

from __future__ import annotations

from datetime import datetime

from src.tools.brief.models import BUCKET_LABELS, BriefItem
from src.tools.macro import TickerMacroSnapshot


def render_markdown(
    date: datetime,
    macro: TickerMacroSnapshot | None,
    items: list[BriefItem],
    top_n: int = 3,
) -> str:
    lines: list[str] = [f"# Daily Brief — {date.strftime('%Y-%m-%d')}", ""]

    lines.extend(_macro_section(macro))

    if not items:
        lines.append("설정된 종목 없음 — playbook.yaml에 holdings/watchlist를 추가하세요.")
        return "\n".join(lines)

    lines.extend(_top_actions_section(items, top_n))

    holdings = [i for i in items if i.kind == "holding"]
    watches = [i for i in items if i.kind == "watch"]
    if holdings:
        lines.append(f"## 보유 ({len(holdings)}종목)")
        lines.append("")
        for item in holdings:
            lines.extend(_item_section(item))
    if watches:
        lines.append(f"## 워치리스트 ({len(watches)}종목)")
        lines.append("")
        for item in watches:
            lines.extend(_item_section(item))

    return "\n".join(lines)


def _macro_section(macro: TickerMacroSnapshot | None) -> list[str]:
    if macro is None:
        return []
    return [
        "## 시장 환경",
        f"VIX {macro.vix:.1f} ({macro.vix_change:+.1f}) · "
        f"Fear&Greed {macro.fear_greed} ({macro.fear_greed_label}) · "
        f"10Y {macro.us_10y:.2f}% · DXY {macro.dxy:.1f}",
        "",
    ]


def _top_actions_section(items: list[BriefItem], top_n: int) -> list[str]:
    lines = [f"## ⚡ 오늘의 액션 (Top {top_n})", ""]
    for rank_no, item in enumerate(items[:top_n], start=1):
        label = BUCKET_LABELS.get(item.bucket, "?")
        marker = f" ⚠{' ·'.join(item.markers)}" if item.markers else ""
        remaining = f" — 남은 조건: {item.remaining_condition}" if item.remaining_condition else ""
        lines.append(f"{rank_no}. [{label}] {item.ticker}{marker}{remaining}")
    lines.append("")
    return lines


def _item_section(item: BriefItem) -> list[str]:
    label = BUCKET_LABELS.get(item.bucket, "?")
    lines: list[str] = []

    if item.action == "error":
        lines.append(f"### {item.ticker} — 데이터 조회 실패")
        lines.append(f"- **오류**: {item.error}")
        lines.append("")
        return lines

    title_extra = ""
    exit_v = item.verdict.exit_verdict if item.verdict else None
    if exit_v is not None and exit_v.current_r is not None:
        title_extra = f" (R={exit_v.current_r:.2f})"
    gate = item.verdict.gate if item.verdict else None
    if gate is not None and gate.quality_grade:
        title_extra = f" (grade {gate.quality_grade})"
    lines.append(f"### {item.ticker} — {label}{title_extra}")

    if item.note:
        lines.append(f"- **메모**: {item.note}")

    # 판정 근거 — 규칙 원문 (LLM과 무관하게 항상 표기)
    if exit_v is not None:
        sig_text = " / ".join(f"{s.code}({s.severity}): {s.detail}" for s in exit_v.signals)
        lines.append(f"- **판정 근거**: {exit_v.detail}" + (f" — {sig_text}" if sig_text else ""))
    elif gate is not None:
        req = [c for c in gate.checklist if c.required]
        check_text = " · ".join(f"{c.name}{'✅' if c.met else '❌' if c.met is False else '—'}" for c in req)
        reason = gate.veto_reason or "전 조건 충족"
        lines.append(f"- **판정 근거**: {check_text} — {reason}")
    if item.remaining_condition:
        lines.append(f"- **남은 조건**: {item.remaining_condition}")

    # 가격/기술 — narrative 있으면 문장, 없으면 수치 원문
    price_part = f"현재가 {item.price:,.2f}" if item.price is not None else ""
    change_part = f" ({item.change_pct:+.1f}%)" if item.change_pct is not None else ""
    narrative = item.narrative
    tech_note = getattr(narrative, "technical_note", None) if narrative else None
    tech_line = f"{price_part}{change_part}"
    if tech_note:
        tech_line = f"{tech_line} · {tech_note}" if tech_line else tech_note
    if tech_line:
        lines.append(f"- **가격/기술**: {tech_line}")

    # 사이징 (게이트 통과 시)
    plan = item.verdict.position_plan if item.verdict else None
    if plan is not None and plan.error is None:
        shares_part = f"{plan.shares}주 " if plan.shares is not None else ""
        lines.append(
            f"- **사이징**: {shares_part}@ {plan.entry:.2f}, stop {plan.stop:.2f} ({plan.stop_basis})"
        )

    # 수급 (KR만, 데이터 있을 때만)
    flow_note = getattr(narrative, "flow_note", None) if narrative else None
    if item.flow is not None:
        fallback = (
            f"외국인 5일 {item.flow.foreign_direction_5d} · 기관 5일 {item.flow.institution_direction_5d}"
        )
        lines.append(f"- **수급(KR)**: {flow_note or fallback}")

    # 뉴스 (있을 때만)
    if item.news:
        news_note = getattr(narrative, "news_note", None) if narrative else None
        titles = " · ".join(f'"{n.title}"' for n in item.news[:3])
        lines.append(f"- **뉴스**: {titles}" + (f" — {news_note}" if news_note else ""))

    # 공시 (있을 때만)
    if item.disclosures:
        disc = " · ".join(f"{d.form_type} {d.description} ({d.date})" for d in item.disclosures[:3])
        lines.append(f"- **공시**: {disc}")

    # 스탑 상태 (보유 + stop_price 있을 때만)
    if item.holding is not None and item.holding.stop_price and item.price:
        dist_pct = (item.price - item.holding.stop_price) / item.holding.stop_price * 100
        near = " ⚠근접" if "스탑 근접" in item.markers else ""
        lines.append(f"- **스탑 상태**: 스탑 {item.holding.stop_price:,.2f} 대비 {dist_pct:+.1f}%{near}")

    # 다음 확인 지점 — narrative 있으면 문장, 없으면 trailing_stop 원문
    next_check = getattr(narrative, "next_check", None) if narrative else None
    if not next_check and exit_v is not None and exit_v.trailing_stop is not None:
        next_check = f"trailing stop(SMA50) {exit_v.trailing_stop:,.2f} 이탈 여부"
    if next_check:
        lines.append(f"- **다음 확인 지점**: {next_check}")

    lines.append("")
    return lines
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/tools/brief/test_render.py -v`
Expected: 전부 PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/brief/render.py tests/tools/brief/test_render.py
git commit -m "feat: brief 마크다운 렌더러 추가 (규칙 원문 fallback 슬롯)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: BriefPipeline 조립

**Files:**
- Create: `src/pipelines/brief.py`
- Test: `tests/pipelines/test_brief.py`

**Interfaces:**
- Consumes:
  - `TechnicalAnalysisTool.execute(ticker, period="3y") -> ToolResult(data=TechnicalResult)` — KR/US 도구 2개를 dict로 주입
  - `PlaybookEngine.evaluate(ticker=, technical_result=, fundamental=None, flow=, zone_set=None, holding=) -> PlaybookVerdict`
  - `MacroTool.execute() -> ToolResult(data=TickerMacroSnapshot)`
  - `NewsTool.execute(ticker, limit=3)`, `DisclosureTool.execute(ticker)`, `FlowTool.execute(code)` (KR만)
  - `HoldingsConfig` (Task 2), scoring 함수들 (Task 3), `generate_brief_narratives` (Task 4), `render_markdown` (Task 5)
  - `is_korean_ticker`, `extract_kr_code` (src/tools/disclosure.py)
- Produces (Task 7이 사용):
  - `BriefPipeline(technical_tools: dict[str, TechnicalAnalysisTool], playbook_engine, macro_tool, news_tool, disclosure_tool, flow_tool, llm: BaseChatModel | None = None)` — `technical_tools` 키는 `"KR"`/`"US"`
  - `async def run(self, config: HoldingsConfig) -> dict` — 키: `date: datetime`, `macro: TickerMacroSnapshot | None`, `items: list[BriefItem]` (rank 정렬됨)
  - `def format_output(self, result: dict) -> str` (render_markdown 위임)
  - `def save_report(self, result: dict) -> Path` — `reports/YYYY-MM/brief_YYYY-MM-DD.md`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/pipelines/test_brief.py` (tests/pipelines/test_deep_dive.py의 AsyncMock 패턴):

```python
"""BriefPipeline 조립 테스트 — 전 도구 목, 부분 실패 격리·LLM fallback 검증."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import ToolResult
from src.pipelines.brief import BriefPipeline
from src.tools.brief.models import BUCKET_LIQUIDATE, BUCKET_REJECTED
from src.tools.macro import TickerMacroSnapshot
from src.tools.playbook.holdings import HoldingEntry, HoldingsConfig, WatchEntry
from src.tools.playbook.models import (
    ExitVerdict,
    GateCheck,
    GateResult,
    MarketRegimeResult,
    PlaybookVerdict,
    RelativeStrengthResult,
)
from src.tools.technical.models import IndicatorSnapshot, TechnicalResult


def _technical(ticker: str, price: float = 100.0, change_pct: float = 1.0) -> TechnicalResult:
    return TechnicalResult(
        ticker=ticker,
        timestamp=datetime(2026, 7, 14),
        snapshot=IndicatorSnapshot(price=price, change_pct=change_pct),
        components={},
    )


def _verdict_holding(ticker: str, action: str = "liquidate") -> PlaybookVerdict:
    return PlaybookVerdict(
        ticker=ticker,
        holding=True,
        market_regime=MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="^GSPC"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=1.0, outperform_6m=1.0, rp_slope_4w=0.1, index_symbol="^GSPC"
        ),
        sector_strength=None,
        canslim=None,
        gate=None,
        position_plan=None,
        exit_verdict=ExitVerdict(
            action=action, signals=[], current_r=None, trailing_stop=None, detail="테스트"
        ),
        headline="",
    )


def _verdict_watch(ticker: str, met: dict[str, bool]) -> PlaybookVerdict:
    checklist = [
        GateCheck(name=n, required=True, met=met[n], reason=f"{n}") for n in ("A", "B", "C", "E")
    ]
    passed = all(met.values())
    return PlaybookVerdict(
        ticker=ticker,
        holding=False,
        market_regime=MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="^GSPC"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=1.0, outperform_6m=1.0, rp_slope_4w=0.1, index_symbol="^GSPC"
        ),
        sector_strength=None,
        canslim=None,
        gate=GateResult(passed=passed, checklist=checklist, quality_grade="A" if passed else None,
                        veto_reason=None if passed else "E: 미충족"),
        position_plan=None,
        exit_verdict=None,
        headline="",
    )


def _config() -> HoldingsConfig:
    return HoldingsConfig(
        krw_capital=None, krw_risk_pct=None, usd_capital=None, usd_risk_pct=None,
        holdings=[HoldingEntry(ticker="AAPL", quantity=5, avg_price=150.0, stop_price=None, currency="USD")],
        watchlist=[WatchEntry(ticker="NVDA", note=None, currency="USD")],
    )


def _pipeline(engine, tech_us=None, llm=None) -> BriefPipeline:
    macro_tool = MagicMock()
    macro_tool.execute = AsyncMock(
        return_value=ToolResult(
            success=True,
            data=TickerMacroSnapshot(
                timestamp=datetime(2026, 7, 14), vix=14.0, vix_change=0.1,
                fear_greed=60, fear_greed_label="Greed", wti=70.0, wti_change=0.0,
                us_10y=4.1, us_2y=4.0, yield_spread=0.1, dxy=104.0, dxy_change=0.0,
            ),
        )
    )
    if tech_us is None:
        tech_us = MagicMock()
        tech_us.execute = AsyncMock(
            side_effect=lambda ticker, **kw: ToolResult(success=True, data=_technical(ticker))
        )
    news_tool = MagicMock()
    news_tool.execute = AsyncMock(return_value=ToolResult(success=True, data=[]))
    disclosure_tool = MagicMock()
    disclosure_tool.execute = AsyncMock(return_value=ToolResult(success=True, data=[]))
    flow_tool = MagicMock()
    flow_tool.execute = AsyncMock(return_value=ToolResult(success=False, data=None, error="no kis"))
    return BriefPipeline(
        technical_tools={"KR": tech_us, "US": tech_us},
        playbook_engine=engine,
        macro_tool=macro_tool,
        news_tool=news_tool,
        disclosure_tool=disclosure_tool,
        flow_tool=flow_tool,
        llm=llm,
    )


@pytest.mark.asyncio
async def test_run_all_targets_included_and_ranked():
    engine = MagicMock()

    async def _eval(*, ticker, holding, **kw):
        if holding is not None:
            return _verdict_holding(ticker, action="liquidate")
        return _verdict_watch(ticker, {"A": True, "B": False, "C": False, "E": False})

    engine.evaluate = AsyncMock(side_effect=_eval)
    pipeline = _pipeline(engine)

    result = await pipeline.run(_config())

    assert {i.ticker for i in result["items"]} == {"AAPL", "NVDA"}
    assert result["items"][0].ticker == "AAPL"  # 청산(버킷1) > 거부(버킷6)
    assert result["items"][0].bucket == BUCKET_LIQUIDATE
    assert result["items"][1].bucket == BUCKET_REJECTED
    assert result["macro"] is not None


@pytest.mark.asyncio
async def test_run_isolates_per_ticker_failure():
    """한 종목 기술분석 실패가 나머지 종목을 막지 않는다."""
    engine = MagicMock()
    engine.evaluate = AsyncMock(
        side_effect=lambda *, ticker, holding, **kw: _verdict_holding(ticker, "hold")
        if holding
        else _verdict_watch(ticker, {"A": True, "B": True, "C": True, "E": True})
    )
    tech = MagicMock()

    async def _tech(ticker, **kw):
        if ticker == "AAPL":
            return ToolResult(success=False, data=None, error="timeout")
        return ToolResult(success=True, data=_technical(ticker))

    tech.execute = AsyncMock(side_effect=_tech)
    pipeline = _pipeline(engine, tech_us=tech)

    result = await pipeline.run(_config())

    by_ticker = {i.ticker: i for i in result["items"]}
    assert by_ticker["AAPL"].action == "error"
    assert "timeout" in by_ticker["AAPL"].error
    assert by_ticker["NVDA"].action == "eligible"


@pytest.mark.asyncio
async def test_run_macro_failure_does_not_block():
    engine = MagicMock()
    engine.evaluate = AsyncMock(
        side_effect=lambda *, ticker, holding, **kw: _verdict_holding(ticker, "hold")
        if holding
        else _verdict_watch(ticker, {"A": True, "B": True, "C": True, "E": True})
    )
    pipeline = _pipeline(engine)
    pipeline.macro_tool.execute = AsyncMock(return_value=ToolResult(success=False, data=None, error="down"))

    result = await pipeline.run(_config())

    assert result["macro"] is None
    assert len(result["items"]) == 2


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_rule_text():
    """LLM 실패 시 narrative 없이 완성 — 규칙 원문 fallback (스펙 §7)."""
    engine = MagicMock()
    engine.evaluate = AsyncMock(
        side_effect=lambda *, ticker, holding, **kw: _verdict_holding(ticker, "hold")
        if holding
        else _verdict_watch(ticker, {"A": True, "B": True, "C": True, "E": True})
    )
    failing_llm = MagicMock()
    failing_llm.with_structured_output.side_effect = RuntimeError("LLM down")
    pipeline = _pipeline(engine, llm=failing_llm)

    result = await pipeline.run(_config())

    assert all(i.narrative is None for i in result["items"])
    md = pipeline.format_output(result)
    assert "NVDA" in md and "AAPL" in md


@pytest.mark.asyncio
async def test_empty_config_returns_empty_items():
    engine = MagicMock()
    pipeline = _pipeline(engine)
    config = HoldingsConfig(
        krw_capital=None, krw_risk_pct=None, usd_capital=None, usd_risk_pct=None
    )
    result = await pipeline.run(config)
    assert result["items"] == []
    engine.evaluate.assert_not_called()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/pipelines/test_brief.py -v`
Expected: FAIL — `ModuleNotFoundError: src.pipelines.brief`

- [ ] **Step 3: brief.py 구현**

`src/pipelines/brief.py`:

```python
"""BriefPipeline — 일일 포트 액션 종합 (스펙: docs/superpowers/specs/2026-07-14-jarvis-brief-design.md).

사실은 코드가, 해석은 LLM이: 액션·순위·근거는 규칙이 확정하고
LLM은 배치 1콜 문장화만 담당한다. 개별 종목·소스 실패는 전체를 막지 않는다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel

from src.llm.analyzer import generate_brief_narratives
from src.tools.brief.models import BriefItem
from src.tools.brief.render import render_markdown
from src.tools.brief.scoring import (
    BONUS_STOP_PROXIMITY,
    BONUS_SURGE,
    bucket_for,
    classify_watch,
    is_stop_proximate,
    rank,
    surge_reason,
)
from src.tools.disclosure import extract_kr_code, is_korean_ticker
from src.tools.playbook.holdings import HoldingEntry, HoldingsConfig

logger = logging.getLogger(__name__)


class BriefPipeline:
    """playbook.yaml(보유+워치) 전 종목 풀 평가 → 버킷 랭킹 → 마크다운 브리핑."""

    def __init__(
        self,
        technical_tools: dict[str, Any],  # {"KR": TechnicalAnalysisTool, "US": ...}
        playbook_engine,
        macro_tool,
        news_tool,
        disclosure_tool,
        flow_tool,
        llm: BaseChatModel | None = None,
    ):
        self.technical_tools = technical_tools
        self.playbook_engine = playbook_engine
        self.macro_tool = macro_tool
        self.news_tool = news_tool
        self.disclosure_tool = disclosure_tool
        self.flow_tool = flow_tool
        self.llm = llm

    async def run(self, config: HoldingsConfig) -> dict[str, Any]:
        date = datetime.now()

        macro = None
        macro_result = await self.macro_tool.execute()
        if macro_result.success:
            macro = macro_result.data
        else:
            logger.warning("매크로 스냅샷 실패 — 시장 환경 섹션 생략: %s", macro_result.error)

        targets: list[tuple[str, HoldingEntry | None, str | None]] = [
            (h.ticker, h, None) for h in config.holdings
        ] + [(w.ticker, None, w.note) for w in config.watchlist]

        items: list[BriefItem] = []
        for ticker, holding, note in targets:  # KIS 동시 호출 금지 → 순차 루프
            items.append(await self._analyze_target(ticker, holding, note))

        ranked = rank(items)

        if self.llm is not None and any(i.action != "error" for i in ranked):
            await self._attach_narratives(ranked)

        return {"date": date, "macro": macro, "items": ranked}

    async def _analyze_target(
        self, ticker: str, holding: HoldingEntry | None, note: str | None
    ) -> BriefItem:
        kind = "holding" if holding is not None else "watch"
        try:
            tool = self.technical_tools["KR" if is_korean_ticker(ticker) else "US"]
            tech_result = await tool.execute(ticker, period="3y")
            if not tech_result.success:
                raise RuntimeError(f"기술분석 실패: {tech_result.error}")
            technical = tech_result.data

            flow = None
            if is_korean_ticker(ticker) and self.flow_tool is not None:
                flow_result = await self.flow_tool.execute(extract_kr_code(ticker))
                flow = flow_result.data if flow_result.success else None

            verdict = await self.playbook_engine.evaluate(
                ticker=ticker,
                technical_result=technical,
                fundamental=None,  # v1: 펀더멘털 미포함 (스펙 §2) — sector는 graceful None
                flow=flow,
                zone_set=None,  # v1: 구조 zone 미포함 — 사이징은 ATR/-8% 기반
                holding=holding,
            )

            news, disclosures = await self._fetch_evidence(ticker)

            price = technical.snapshot.price
            change_pct = technical.snapshot.change_pct

            remaining_condition = None
            if holding is not None:
                action = verdict.exit_verdict.action if verdict.exit_verdict else "hold"
                has_warn = bool(verdict.exit_verdict and verdict.exit_verdict.signals)
            else:
                action, remaining_condition = classify_watch(verdict.gate)
                has_warn = False

            markers: list[str] = []
            bonus = 0
            stop_price = holding.stop_price if holding else None
            if is_stop_proximate(price, stop_price):
                markers.append("스탑 근접")
                bonus += BONUS_STOP_PROXIMITY
            surge = surge_reason(kind, change_pct)
            if surge:
                markers.append(surge)
                bonus += BONUS_SURGE

            return BriefItem(
                ticker=ticker,
                kind=kind,
                action=action,
                bucket=bucket_for(kind, action, has_warn_signals=has_warn),
                bonus=bonus,
                markers=markers,
                note=note,
                holding=holding,
                verdict=verdict,
                news=news,
                disclosures=disclosures,
                flow=flow,
                price=price,
                change_pct=change_pct,
                remaining_condition=remaining_condition,
            )
        except Exception as e:
            logger.warning("brief 종목 분석 실패 %s: %s", ticker, e)
            return BriefItem(
                ticker=ticker,
                kind=kind,
                action="error",
                bucket=bucket_for(kind, "error"),
                note=note,
                holding=holding,
                error=str(e),
            )

    async def _fetch_evidence(self, ticker: str) -> tuple[list, list]:
        """뉴스·공시 — 표기 전용, 실패해도 판정에 영향 없음."""
        results = await asyncio.gather(
            self.news_tool.execute(ticker, limit=3),
            self.disclosure_tool.execute(ticker),
            return_exceptions=True,
        )
        news_r, disc_r = results
        news = news_r.data if not isinstance(news_r, Exception) and news_r.success else []
        disclosures = disc_r.data if not isinstance(disc_r, Exception) and disc_r.success else []
        return news, disclosures

    async def _attach_narratives(self, items: list[BriefItem]) -> None:
        """LLM 배치 1콜. 실패 시 narrative 없이 진행 — 렌더러가 규칙 원문으로 fallback."""
        try:
            facts = [self._facts_for(i) for i in items if i.action != "error"]
            output = await generate_brief_narratives(
                json.dumps({"items": facts}, ensure_ascii=False), llm=self.llm
            )
            by_ticker = {n.ticker: n for n in output.narratives}
            for item in items:
                item.narrative = by_ticker.get(item.ticker)
        except Exception as e:
            logger.warning("LLM 문장화 실패 — 규칙 원문으로 진행: %s", e)

    @staticmethod
    def _facts_for(item: BriefItem) -> dict[str, Any]:
        exit_v = item.verdict.exit_verdict if item.verdict else None
        gate = item.verdict.gate if item.verdict else None
        return {
            "ticker": item.ticker,
            "kind": item.kind,
            "action": item.action,
            "price": item.price,
            "change_pct": item.change_pct,
            "markers": item.markers,
            "exit_detail": exit_v.detail if exit_v else None,
            "exit_signals": [f"{s.code}: {s.detail}" for s in exit_v.signals] if exit_v else [],
            "gate_veto": gate.veto_reason if gate else None,
            "remaining_condition": item.remaining_condition,
            "flow": (
                f"외인5일 {item.flow.foreign_direction_5d}, 기관5일 {item.flow.institution_direction_5d}"
                if item.flow
                else None
            ),
            "news_titles": [n.title for n in item.news[:3]],
        }

    def format_output(self, result: dict[str, Any]) -> str:
        return render_markdown(result["date"], result["macro"], result["items"])

    def save_report(self, result: dict[str, Any]) -> Path:
        """reports/YYYY-MM/brief_YYYY-MM-DD.md 저장 (ScreenerPipeline.save_report 패턴)."""
        date: datetime = result["date"]
        dir_path = Path("reports") / date.strftime("%Y-%m")
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"brief_{date.strftime('%Y-%m-%d')}.md"
        file_path.write_text(self.format_output(result), encoding="utf-8")
        return file_path
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/pipelines/test_brief.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 전체 테스트 회귀 확인**

Run: `uv run pytest`
Expected: 전부 PASS

- [ ] **Step 6: Commit**

```bash
git add src/pipelines/brief.py tests/pipelines/test_brief.py
git commit -m "feat: BriefPipeline 조립 (전 종목 풀 평가, 부분 실패 격리, LLM fallback)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: CLI `jarvis brief` 명령

**Files:**
- Modify: `src/cli/main.py` (신규 `run_brief` 코루틴 + `@app.command() brief` — `analyze`/`run_deep_dive` 패턴, 1024행 부근 참고)
- Test: `tests/integration/test_brief_command.py`

**Interfaces:**
- Consumes: `BriefPipeline` (Task 6), `load_holdings` (Task 2), 기존 CLI 조립 부품 — `KISProvider`, `KISProviderWrapper`, `YFinanceProvider`, `TechnicalScorer`, `TechnicalAnalysisTool`, `IndexProvider`, `FmpProvider`, `SECDisclosureFetcher`/`DARTDisclosureFetcher`/`DisclosureTool`, `FlowTool`, `MacroTool`, `NewsTool`, `LLMProvider.create`
- Produces: CLI 명령 `jarvis brief [--provider openai|anthropic] [--no-llm]`

- [ ] **Step 1: 실패하는 등록 테스트 작성**

`tests/integration/test_brief_command.py`:

```python
from typer.testing import CliRunner

from src.cli.main import app

runner = CliRunner()


def test_brief_command_registered():
    result = runner.invoke(app, ["brief", "--help"])
    assert result.exit_code == 0
    assert "brief" in result.output.lower() or "브리핑" in result.output
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/integration/test_brief_command.py -v`
Expected: FAIL — exit_code 2 (명령 없음)

- [ ] **Step 3: CLI 구현**

`src/cli/main.py`에 추가 — import 구역에 `from src.pipelines.brief import BriefPipeline`, 명령들 근처에:

```python
async def run_brief(provider: str, use_llm: bool) -> dict:
    """brief 파이프라인 조립·실행. run_deep_dive와 동일한 도구 조립 패턴."""
    from src.providers.index_provider import IndexProvider
    from src.providers.kis import KISProvider
    from src.providers.kis_wrapper import KISProviderWrapper
    from src.providers.yfinance_provider import YFinanceProvider
    from src.tools.flow import FlowTool
    from src.tools.macro import MacroTool
    from src.tools.playbook.engine import PlaybookEngine
    from src.tools.playbook.holdings import load_holdings
    from src.tools.technical.scorer import TechnicalScorer
    from src.tools.technical.tool import TechnicalAnalysisTool

    config = load_holdings()
    if not config.holdings and not config.watchlist:
        raise ValueError("playbook.yaml에 holdings/watchlist가 없습니다")

    kis_key, kis_secret = os.getenv("KIS_APP_KEY"), os.getenv("KIS_APP_SECRET")
    kis_provider = KISProvider(app_key=kis_key, app_secret=kis_secret) if kis_key and kis_secret else None

    scorer = TechnicalScorer()
    us_tool = TechnicalAnalysisTool(provider=YFinanceProvider(), scorer=scorer)
    kr_tool = (
        TechnicalAnalysisTool(provider=KISProviderWrapper(kis_provider), scorer=scorer)
        if kis_provider
        else us_tool  # KIS 키 없으면 yfinance fallback (KR은 .KS 접미사 필요)
    )

    fmp_provider = None
    fmp_api_key = os.getenv("FMP_API_KEY")
    if fmp_api_key:
        with contextlib.suppress(Exception):
            from src.providers.fmp_provider import FmpProvider

            fmp_provider = FmpProvider(api_key=fmp_api_key)

    engine = PlaybookEngine(
        index_provider=IndexProvider(),
        fmp_provider=fmp_provider,
        kis_provider=kis_provider,
        usd_capital=config.usd_capital,
        usd_risk_pct=config.usd_risk_pct or 0.01,
        krw_capital=config.krw_capital,
        krw_risk_pct=config.krw_risk_pct or 0.01,
    )

    sec_fetcher = SECDisclosureFetcher()
    opendart_key = os.getenv("OPENDART_API_KEY")
    dart_fetcher = DARTDisclosureFetcher(api_key=opendart_key) if opendart_key else None

    llm = None
    if use_llm:
        try:
            llm = LLMProvider.create(provider=provider, temperature=0)
        except Exception as e:
            console.print(f"[yellow]LLM 초기화 실패 — 규칙 원문으로 진행: {e}[/yellow]")

    pipeline = BriefPipeline(
        technical_tools={"KR": kr_tool, "US": us_tool},
        playbook_engine=engine,
        macro_tool=MacroTool(),
        news_tool=NewsTool(),
        disclosure_tool=DisclosureTool(sec_fetcher=sec_fetcher, dart_fetcher=dart_fetcher),
        flow_tool=FlowTool(kis_provider=kis_provider),
        llm=llm,
    )
    result = await pipeline.run(config)
    result["_pipeline"] = pipeline
    return result


@app.command()
def brief(
    provider: str = typer.Option("openai", "--provider", "-p", help="LLM provider (openai|anthropic)"),
    no_llm: bool = typer.Option(False, "--no-llm", help="LLM 문장화 없이 규칙 원문만 출력"),
):
    """일일 포트 액션 브리핑 — playbook.yaml 보유+워치 전 종목 평가."""
    console.print("[bold]Daily brief 생성 중...[/bold]")
    try:
        result = asyncio.run(run_brief(provider, use_llm=not no_llm))
        pipeline = result.pop("_pipeline")
        console.print(Markdown(pipeline.format_output(result)))
        report_path = pipeline.save_report(result)
        console.print(f"\n[green]리포트 저장: {report_path}[/green]")
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
```

주의: `SECDisclosureFetcher`, `DARTDisclosureFetcher`, `DisclosureTool`, `NewsTool`, `LLMProvider`, `Markdown`, `contextlib`, `os`, `asyncio`는 main.py에 이미 import되어 있는지 확인하고 없으면 추가.

- [ ] **Step 4: 통과 + 회귀 확인**

Run: `uv run pytest tests/integration/test_brief_command.py -v && uv run pytest`
Expected: 전부 PASS

- [ ] **Step 5: 수동 스모크 테스트** (playbook.yaml에 실제 종목 1-2개 필요)

Run: `uv run jarvis brief --no-llm`
Expected: 터미널에 브리핑 마크다운 출력 + `reports/YYYY-MM/brief_*.md` 생성. 실패 종목이 있어도 전체가 완성되는지 확인

- [ ] **Step 6: Commit**

```bash
git add src/cli/main.py tests/integration/test_brief_command.py
git commit -m "feat: jarvis brief CLI 명령 추가

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: PortfolioPipeline 제거 (별도 커밋)

**Files:**
- Delete: `src/pipelines/portfolio.py`, `src/tools/portfolio.py`, `tests/pipelines/test_portfolio.py`, `tests/tools/test_portfolio.py`
- Modify: `src/cli/main.py` — import 2줄(line 18 `PortfolioPipeline`, line 29 `PortfolioTool`), `run_portfolio_monitoring`(1188-1207), `portfolio` 명령(1210-1231) 삭제. ※ line 22 `KISProvider` import는 다른 명령이 사용하므로 유지
- Modify: `tests/integration/test_e2e_plan3.py` — `test_portfolio_command`(17-21) 삭제
- 보존: `KISProvider.get_balance()`(src/providers/kis.py:253), `PortfolioPosition`/`PortfolioBalance`(src/providers/kis_models.py) — provider 레이어는 유지 (스펙 D7)

- [ ] **Step 1: 삭제 실행**

```bash
git rm src/pipelines/portfolio.py src/tools/portfolio.py tests/pipelines/test_portfolio.py tests/tools/test_portfolio.py
```

`src/cli/main.py`에서 위 명시된 import 2줄 + `run_portfolio_monitoring` + `portfolio` 명령 함수 삭제. `tests/integration/test_e2e_plan3.py`에서 `test_portfolio_command` 삭제.

- [ ] **Step 2: 잔여 참조 확인**

Run: `grep -rn "PortfolioPipeline\|PortfolioTool\|run_portfolio_monitoring" src/ tests/ docs/FEATURES.md docs/CLI_USAGE.md`
Expected: src/·tests/에서 0건 (docs는 Task 9에서 갱신)

- [ ] **Step 3: 전체 테스트 통과 확인**

Run: `uv run pytest`
Expected: 전부 PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: PortfolioPipeline 제거 (KIS 잔고 전제 소멸, brief가 대체)

get_balance() provider 메서드와 kis_models는 보존.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: 문서 갱신 + 마무리

**Files:**
- Modify: `docs/FEATURES.md` — `jarvis brief` 기능 섹션 추가(입력: playbook.yaml / 출력: reports/YYYY-MM/brief_*.md / 데이터소스: 기존 도구 재사용), `portfolio` 섹션 제거
- Modify: `docs/CLI_USAGE.md` — `brief` 명령 사용법·옵션(`--provider`, `--no-llm`)·playbook.yaml watchlist 예시 추가, `portfolio` 제거
- Modify: `docs/worklog/jarvis-brief.md` — 구현 완료 시점 기록

- [ ] **Step 1: FEATURES.md 갱신** — 기존 기능 섹션 형식을 따라 brief 추가, portfolio 삭제

- [ ] **Step 2: CLI_USAGE.md 갱신** — 사용 예시:

````markdown
## brief — 일일 포트 액션 브리핑

```bash
uv run jarvis brief                # LLM 문장화 포함 (기본 openai)
uv run jarvis brief --no-llm       # 규칙 원문만 (LLM 키 불필요)
uv run jarvis brief -p anthropic
```

playbook.yaml에 보유·워치리스트를 설정한다:

```yaml
holdings:
  - ticker: "005930"
    quantity: 10
    avg_price: 72000
    stop_price: 65000   # 선택
watchlist:
  - ticker: NVDA
    note: "AI 반도체 대장"   # 선택
```
````

- [ ] **Step 3: Commit**

```bash
git add docs/FEATURES.md docs/CLI_USAGE.md docs/worklog/jarvis-brief.md
git commit -m "docs: jarvis brief 기능 문서화, portfolio 문서 제거

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: PR 준비** — push 전 `/change-record` 스킬로 `docs/changes/` 변경 기록 작성 + `docs/changes/INDEX.md` 갱신 (프로젝트 규칙 — pre-push 훅이 FEATURES.md/changes 누락 시 push 차단). PR 본문에 스펙 문서 링크 포함.

---

## Self-Review 결과

- **Spec coverage**: §2 포함 항목 전부 태스크 매핑 — 선행 버그수정(T1), watchlist 로더(T2), 단일 진입점 판정(T6), 버킷 랭킹(T3), 근거 슬롯(T5·T6), LLM 배치+fallback(T4·T6), 마크다운 출력(T5·T7), PortfolioPipeline 제거(T8). §7 에러 처리 — T6 테스트(부분 실패·매크로 실패·LLM 실패·빈 설정). §8 테스트 전략 1~5 — T1·T3·T2·T6·T6 순서로 커버
- **Placeholder scan**: TBD/TODO 없음, 전 코드 스텝에 실제 코드 포함
- **Type consistency**: `BriefItem` 필드·`classify_watch` 반환형·`technical_tools` dict 키("KR"/"US")·`generate_brief_narratives(facts_json: str, llm)` 시그니처가 태스크 간 일치 확인
