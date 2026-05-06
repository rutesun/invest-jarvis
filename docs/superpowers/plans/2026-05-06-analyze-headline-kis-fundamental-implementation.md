# Analyze Headline + KIS Fundamental Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `jarvis analyze`에서 상단 `핵심 변수`를 짧은 headline 기반으로 바꾸고, 한국 주식 펀더멘털 원천을 KIS 재무 API 5종으로 전환한다.

**Architecture:** 판단 레이어는 `FactorAssessment.summary`와 분리된 `headline`을 추가해 상단 요약과 상세 설명의 책임을 분리한다. 펀더멘털 레이어는 `FundamentalTool` 내부에서 한국/해외 경로를 분기하고, 한국 주식은 KIS 재무 API 응답을 공통 `FundamentalSnapshot`으로 정규화한 뒤 기존 LLM 요약 흐름에 연결한다.

**Tech Stack:** Python 3.12, Pydantic, httpx, yfinance, Typer, pytest, uv, KIS OpenAPI

---

## 파일 구조

### 새로 만드는 파일
- `tests/tools/test_fundamental_kis.py` - 한국 주식 KIS 재무 fetcher 매핑, 누락값, 분기 계산 테스트

### 수정하는 파일
- `src/providers/kis.py` - KIS 재무 API 5종 호출 메서드 추가
- `src/tools/fundamental.py` - 한국/해외 분기, KIS 응답 정규화, 기존 yfinance 경로 분리
- `src/pipelines/analyze_decision.py` - `headline` 필드 추가, 팩터별 짧은 headline 생성 규칙 추가
- `src/cli/main.py` - 상단 `핵심 변수`를 headline 기반으로 렌더링, 펀더멘털 `N/A` 출력 유지 검증
- `tests/tools/test_fundamental.py` - 기존 yfinance 경로 회귀 테스트 보강
- `tests/pipelines/test_analyze_decision.py` - headline 우선 사용 테스트 추가
- `tests/cli/test_analyze_output.py` - 상단에는 headline만, 상세에는 summary 유지 테스트 추가
- `docs/CLI_USAGE.md` - 한국 주식 펀더멘털 원천이 KIS이고 상단 핵심 변수가 headline 기준이라는 설명 추가

---

## 한눈에 보는 작업 흐름

### Task 1
- headline 필드를 추가하고 상단/상세 텍스트 책임을 분리한다.

### Task 2
- KIS 재무 API 5종 호출과 `FundamentalSnapshot` 정규화를 구현한다.

### Task 3
- pipeline/CLI에 headline과 KIS snapshot을 연결하고 출력 규칙을 정리한다.

### Task 4
- 실제 회귀 테스트와 문서를 마무리한다.

---

### Task 1: headline 필드와 판단 라벨 분리

**Files:**
- Modify: `src/pipelines/analyze_decision.py`
- Modify: `tests/pipelines/test_analyze_decision.py`
- Modify: `tests/cli/test_analyze_output.py`

- [ ] **Step 1: headline 우선 사용 테스트를 먼저 추가**

```python
# tests/pipelines/test_analyze_decision.py
def test_build_decision_summary_prefers_headline_for_core_variables():
    summary = build_decision_summary(
        leader_label="valuation",
        assessments=[
            FactorAssessment(
                factor_type="valuation",
                role="보조",
                freshness_score=3,
                magnitude_score=3,
                actionability_score=2,
                total_score=7,
                headline="고평가 부담",
                summary="전반적으로 강력한 재무 성과를 보여주지만 현재 밸류는 부담스럽다.",
                role_reason="고평가 해석이라 공격적 추격을 경계해야 함",
                evidence=["valuation=고평가"],
                bias="bearish",
            ),
            FactorAssessment(
                factor_type="flow",
                role="보조",
                freshness_score=4,
                magnitude_score=2,
                actionability_score=4,
                total_score=7,
                headline="기관 매수 우위",
                summary="외인/기관 수급이 현재 흐름을 뒷받침함",
                role_reason="한 축의 수급은 우호적이지만 일치도는 제한적임",
                evidence=["기관 5일: 매수"],
                bias="bullish",
            ),
        ],
    )

    assert summary.core_variables == ["고평가 부담", "기관 매수 우위"]
```

```python
# tests/cli/test_analyze_output.py
def test_format_deep_dive_output_uses_headline_in_top_summary_only():
    summary = AnalyzeDecisionSummary(
        leader="혼합",
        core_variables=["고평가 부담", "기관 매수 우위"],
        action="관망",
        timing="조정_대기",
        action_sentence="지금 추격보다 핵심 레벨 확인 후 접근이 유리",
    )

    output = _format_top_summary(summary)

    assert "고평가 부담" in output
    assert "기관 매수 우위" in output
```

- [ ] **Step 2: 새 테스트가 실패하는지 확인**

Run: `uv run pytest tests/pipelines/test_analyze_decision.py::test_build_decision_summary_prefers_headline_for_core_variables tests/cli/test_analyze_output.py::test_format_deep_dive_output_uses_headline_in_top_summary_only -v`  
Expected: `ValidationError` for unexpected field `headline` or assertion failure on `core_variables`

- [ ] **Step 3: FactorAssessment에 headline을 추가하고 core_variables 계산을 바꾼다**

```python
# src/pipelines/analyze_decision.py
class FactorAssessment(BaseModel):
    factor_type: str
    role: str
    freshness_score: int = Field(ge=0, le=5)
    magnitude_score: int = Field(ge=0, le=5)
    actionability_score: int = Field(ge=0, le=5)
    total_score: int = Field(ge=0, le=15)
    headline: str | None = None
    summary: str
    role_reason: str
    evidence: list[str]
    bias: str = "neutral"


def _compact_summary(text: str, limit: int = 18) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else f"{compact[:limit].rstrip()}..."


def _pick_core_variable_label(assessment: FactorAssessment) -> str:
    return assessment.headline or _compact_summary(assessment.summary)


def build_decision_summary(
    leader_label: str,
    assessments: list[FactorAssessment],
) -> AnalyzeDecisionSummary:
    ...
    core_variables = [
        _pick_core_variable_label(assessment) for assessment in prioritized_assessments[:2]
    ]
    ...
```

- [ ] **Step 4: 팩터별 headline 생성 규칙을 추가한다**

```python
# src/pipelines/analyze_decision.py
def _technical_headline(total_score: int, rsi: float | None, bias: str) -> str:
    if bias == "bearish":
        return "추세 약화"
    if rsi is not None and rsi >= 80:
        return "단기 과열"
    if total_score >= 100:
        return "신고가 돌파"
    return "가격 모멘텀"


def _event_headline(total_score: int, bias: str, evidence: list[str]) -> str:
    if total_score == 0:
        return "신규 재료 제한적"
    if bias == "bearish":
        return "규제 리스크"
    if any("계약" in item or "수주" in item for item in evidence):
        return "공급계약 재료"
    return "이벤트 부각"
```

- [ ] **Step 5: 기존 assessment builder가 headline을 채우도록 수정한다**

```python
# src/pipelines/analyze_decision.py
return FactorAssessment(
    factor_type="technical",
    role=role,
    freshness_score=4 if score > 0 else 1,
    magnitude_score=4 if score > 0 else 1,
    actionability_score=3 if score > 0 else 1,
    total_score=score,
    headline=_technical_headline(total_score, rsi, bias),
    summary=summary,
    role_reason=role_reason,
    evidence=[f"technical total_score={total_score}", rsi_evidence],
    bias=bias,
)
```

- [ ] **Step 6: Task 1 전체 테스트를 실행한다**

Run: `uv run pytest tests/pipelines/test_analyze_decision.py tests/cli/test_analyze_output.py -v`  
Expected: 기존 judgment-first 테스트 + 새 headline 테스트 통과

- [ ] **Step 7: 커밋한다**

```bash
git add src/pipelines/analyze_decision.py tests/pipelines/test_analyze_decision.py tests/cli/test_analyze_output.py
git commit -m "feat(analyze): split headline from detail" -m "- 상단 핵심 변수용 headline 필드를 추가함
- core_variables가 headline을 우선 사용하도록 변경함
- 팩터별 짧은 판단 라벨 생성 규칙을 추가함"
```

---

### Task 2: 한국 주식 KIS 재무 fetcher 구현

**Files:**
- Modify: `src/providers/kis.py`
- Modify: `src/tools/fundamental.py`
- Create: `tests/tools/test_fundamental_kis.py`
- Modify: `tests/tools/test_fundamental.py`

- [ ] **Step 1: 한국 주식 KIS 경로 테스트를 먼저 추가한다**

```python
# tests/tools/test_fundamental_kis.py
import pytest

from src.tools.fundamental import FundamentalTool


@pytest.mark.asyncio
async def test_fundamental_tool_uses_kis_for_korean_ticker():
    tool = FundamentalTool()
    tool._fetch_kis_fundamentals = pytest.AsyncMock(  # type: ignore[attr-defined]
        return_value={"roe": 0.23}
    )
    tool._fetch_yfinance_fundamentals = pytest.AsyncMock()  # type: ignore[attr-defined]

    await tool.execute("033100.KQ")

    tool._fetch_kis_fundamentals.assert_awaited_once_with("033100.KQ")
    tool._fetch_yfinance_fundamentals.assert_not_awaited()
```

```python
# tests/tools/test_fundamental_kis.py
def test_normalize_kis_snapshot_sets_missing_values_to_none():
    tool = FundamentalTool()
    snapshot = tool._normalize_kis_snapshot(  # type: ignore[attr-defined]
        ticker="033100.KQ",
        profit_ratio={"roe": "25.3"},
        financial_ratio={},
        other_major_ratios={},
        income_statement={},
        balance_sheet={},
    )

    assert snapshot.roe == 0.253
    assert snapshot.current_ratio is None
    assert snapshot.quick_ratio is None
```

- [ ] **Step 2: 새 테스트가 실패하는지 확인한다**

Run: `uv run pytest tests/tools/test_fundamental_kis.py -v`  
Expected: `AttributeError` for missing `_fetch_kis_fundamentals` or `_normalize_kis_snapshot`

- [ ] **Step 3: KIS provider에 재무 API 5종 호출 메서드를 추가한다**

```python
# src/providers/kis.py
    async def get_financial_ratio(self, ticker: str) -> dict:
        return await self._get_finance_endpoint(
            path="/uapi/domestic-stock/v1/finance/financial-ratio",
            tr_id="FHKST66430100",
            ticker=ticker,
        )

    async def get_profit_ratio(self, ticker: str) -> dict:
        return await self._get_finance_endpoint(
            path="/uapi/domestic-stock/v1/finance/profit-ratio",
            tr_id="FHKST66430300",
            ticker=ticker,
        )

    async def get_other_major_ratios(self, ticker: str) -> dict:
        return await self._get_finance_endpoint(
            path="/uapi/domestic-stock/v1/finance/other-major-ratios",
            tr_id="FHKST66430500",
            ticker=ticker,
        )
```

```python
# src/providers/kis.py
    async def _get_finance_endpoint(self, path: str, tr_id: str, ticker: str) -> dict:
        token = await self._get_access_token()
        url = f"{self.BASE_URL}{path}"
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "Content-Type": "application/json; charset=utf-8",
        }
        params = {
            "FID_DIV_CLS_CODE": "0",
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker.replace(".KS", "").replace(".KQ", ""),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
```

- [ ] **Step 4: FundamentalTool을 한국/해외 경로로 분기한다**

```python
# src/tools/fundamental.py
from src.tools.disclosure import is_korean_ticker
from src.providers.kis import KISProvider


class FundamentalTool(BaseTool):
    def __init__(self, kis_provider: KISProvider | None = None):
        self.kis_provider = kis_provider

    async def execute(self, ticker: str, **kwargs) -> ToolResult:
        try:
            if is_korean_ticker(ticker) and self.kis_provider is not None:
                snapshot = await self._fetch_kis_fundamentals(ticker)
            else:
                loop = asyncio.get_running_loop()
                snapshot = await loop.run_in_executor(
                    None, partial(self._fetch_yfinance_fundamentals, ticker)
                )
            return ToolResult(success=True, data=snapshot)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
```

- [ ] **Step 5: KIS 응답을 FundamentalSnapshot으로 정규화한다**

```python
# src/tools/fundamental.py
    def _normalize_kis_snapshot(
        self,
        *,
        ticker: str,
        profit_ratio: dict,
        financial_ratio: dict,
        other_major_ratios: dict,
        income_statement: dict,
        balance_sheet: dict,
    ) -> FundamentalSnapshot:
        def as_float(value: str | float | None, scale: float = 1.0) -> float | None:
            if value in (None, "", "-"):
                return None
            return float(value) / scale

        return FundamentalSnapshot(
            sector=None,
            industry=None,
            pe_ratio=as_float(other_major_ratios.get("per")),
            pb_ratio=as_float(other_major_ratios.get("pbr")),
            ps_ratio=as_float(other_major_ratios.get("psr")),
            roe=as_float(profit_ratio.get("roe"), 100.0),
            roa=as_float(profit_ratio.get("roa"), 100.0),
            operating_margin=as_float(profit_ratio.get("opr_prfi_rt"), 100.0),
            profit_margin=as_float(profit_ratio.get("net_prfi_rt"), 100.0),
            debt_to_equity=as_float(financial_ratio.get("debt_rate")),
            current_ratio=as_float(financial_ratio.get("current_ratio")),
            quick_ratio=as_float(financial_ratio.get("quick_ratio")),
            market_cap=None,
            free_cash_flow=None,
            operating_cash_flow=None,
            fcf_yield=None,
            dividend_yield=None,
            payout_ratio=None,
            quarterly_data=self._build_kis_quarterly_data(income_statement),
        )
```

- [ ] **Step 6: KIS 경로와 기존 yfinance 경로 테스트를 함께 돌린다**

Run: `uv run pytest tests/tools/test_fundamental.py tests/tools/test_fundamental_kis.py -v`  
Expected: 한국 주식 KIS 경로, 누락값 `None`, 미국 주식 yfinance 회귀 테스트 통과

- [ ] **Step 7: 커밋한다**

```bash
git add src/providers/kis.py src/tools/fundamental.py tests/tools/test_fundamental.py tests/tools/test_fundamental_kis.py
git commit -m "feat(fundamental): use KIS for korean stocks" -m "- 한국 주식 펀더멘털을 KIS 재무 API 5종으로 조회하도록 추가함
- KIS 응답을 FundamentalSnapshot으로 정규화함
- 미국 주식은 기존 yfinance 경로를 유지함"
```

---

### Task 3: pipeline과 CLI에 headline/KIS 스냅샷 연결

**Files:**
- Modify: `src/cli/main.py`
- Modify: `src/pipelines/deep_dive.py`
- Modify: `tests/cli/test_cli.py`
- Modify: `tests/cli/test_analyze_output.py`

- [ ] **Step 1: CLI headline/N/A 출력 테스트를 먼저 추가한다**

```python
# tests/cli/test_analyze_output.py
def test_format_deep_dive_output_shows_headline_in_top_summary_and_detail_in_factor_section():
    summary = AnalyzeDecisionSummary(
        leader="혼합",
        core_variables=["고평가 부담", "기관 매수 우위"],
        action="관망",
        timing="조정_대기",
        action_sentence="지금 추격보다 핵심 레벨 확인 후 접근이 유리",
    )
    assessment = FactorAssessment(
        factor_type="valuation",
        role="보조",
        freshness_score=3,
        magnitude_score=3,
        actionability_score=2,
        total_score=7,
        headline="고평가 부담",
        summary="전반적으로 강력한 재무 성과를 보여주지만 현재 밸류는 부담스럽다.",
        role_reason="고평가 해석이라 공격적 추격을 경계해야 함",
        evidence=["valuation=고평가"],
        bias="bearish",
    )

    top = _format_top_summary(summary)
    detail = _format_factor_section([assessment])

    assert "고평가 부담" in top
    assert "전반적으로 강력한 재무 성과" in detail
```

```python
# tests/cli/test_cli.py
def test_cli_analyze_command_shows_na_for_missing_korean_fundamentals():
    ...
    mock_fundamental = type(
        "Fundamental",
        (),
        {"sector": None, "industry": None, "market_cap": None, "roe": None, "quarterly_data": None},
    )()
    mock_result["fundamental"] = mock_fundamental
    mock_result["fundamental_summary"] = None
    ...
    assert "N/A" in result.stdout
```

- [ ] **Step 2: 새 테스트가 실패하는지 확인한다**

Run: `uv run pytest tests/cli/test_analyze_output.py tests/cli/test_cli.py -v`  
Expected: assertion failure because top summary/detail split or N/A rendering is incomplete

- [ ] **Step 3: CLI 상단 요약과 펀더멘털 렌더링을 정리한다**

```python
# src/cli/main.py
def _format_top_summary(decision_summary) -> str:
    lines = [
        "## 판단 요약",
        "",
        f"- **주도 팩터**: {_format_factor_label(decision_summary.leader)}",
        f"- **핵심 변수**: {', '.join(decision_summary.core_variables)}",
        f"- **액션**: {decision_summary.action} | {_format_timing_label(decision_summary.timing)}",
        f"- **한줄 판단**: {decision_summary.action_sentence}",
    ]
    if decision_summary.defer_reason:
        lines.append(f"- **보류 이유**: {decision_summary.defer_reason}")
    return "\n".join(lines)
```

```python
# src/cli/main.py
def _format_metric_value(metric_name: str, value: float | None) -> str:
    if value is None:
        return "N/A"
    ...
```

- [ ] **Step 4: DeepDivePipeline 생성 시 KIS provider를 FundamentalTool에도 넣는다**

```python
# src/cli/main.py
    if is_korean_stock and kis_key and kis_secret:
        kis_provider = KISProvider(app_key=kis_key, app_secret=kis_secret)
        fundamental_tool = FundamentalTool(kis_provider=kis_provider)
    else:
        fundamental_tool = FundamentalTool()
```

- [ ] **Step 5: 관련 테스트를 다시 돌린다**

Run: `uv run pytest tests/cli/test_analyze_output.py tests/cli/test_cli.py tests/pipelines/test_deep_dive.py -v`  
Expected: headline 상단 출력, 상세 summary 유지, 한국 주식 `N/A` 렌더링 테스트 통과

- [ ] **Step 6: 커밋한다**

```bash
git add src/cli/main.py src/pipelines/deep_dive.py tests/cli/test_analyze_output.py tests/cli/test_cli.py
git commit -m "feat(cli): render headline-based judgment summary" -m "- 상단 핵심 변수를 headline 기준으로 출력하도록 변경함
- 액션과 한줄 판단을 분리해 가독성을 높임
- 한국 주식 누락 펀더멘털은 N/A로 표시하도록 유지함"
```

---

### Task 4: 회귀 검증과 문서 마무리

**Files:**
- Modify: `docs/CLI_USAGE.md`
- Modify: `tests/tools/test_fundamental_kis.py`
- Modify: `tests/pipelines/test_analyze_decision.py`

- [ ] **Step 1: 문서 업데이트 테스트 관점 체크리스트를 추가한다**

```markdown
# docs/CLI_USAGE.md
### analyze

- 상단 `핵심 변수`는 짧은 headline 기준으로 출력됩니다.
- 한국 주식 펀더멘털은 KIS 재무 API를 사용합니다.
- KIS에서 제공하지 않는 지표는 `N/A`로 표시됩니다.
```

- [ ] **Step 2: 실제 한국 주식 headline 회귀 테스트를 추가한다**

```python
# tests/pipelines/test_analyze_decision.py
def test_build_valuation_assessment_sets_short_headline_for_bearish_valuation():
    assessment = build_valuation_assessment(
        FundamentalSummaryOutput(
            summary="전반적으로 강력한 재무 성과를 보여주지만 현재 밸류는 부담스럽다.",
            strengths=["높은 ROE"],
            weaknesses=["매출 성장 둔화"],
            valuation_assessment="고평가",
            confidence=0.85,
        )
    )

    assert assessment.headline == "고평가 부담"
    assert "전반적으로 강력한 재무 성과" in assessment.summary
```

- [ ] **Step 3: 전체 회귀 테스트를 실행한다**

Run: `uv run pytest`  
Expected: 전체 테스트 통과

- [ ] **Step 4: 실제 명령으로 한국 주식 샘플을 검증한다**

Run: `OPENAI_API_KEY=... MPLCONFIGDIR=/private/tmp/mpl-jarvis uv run jarvis analyze 제룡전기`  
Expected:
- 상단 `핵심 변수`에 긴 문단 대신 `고평가 부담`, `기관 매수 우위` 같은 짧은 라벨 표시
- 한국 주식 펀더멘털 누락 항목은 `N/A`
- 기존처럼 `401` 없이 완료되면 차트 파일까지 생성

- [ ] **Step 5: 최종 커밋한다**

```bash
git add docs/CLI_USAGE.md tests/pipelines/test_analyze_decision.py tests/tools/test_fundamental_kis.py
git commit -m "docs: document headline and KIS fundamentals" -m "- analyze 핵심 변수 headline 규칙을 문서에 반영함
- 한국 주식 KIS 펀더멘털 원천과 N/A 규칙을 문서화함
- 최종 회귀 테스트와 실제 한국 종목 검증을 마무리함"
```

