# Daily Report V2 구현 계획

> **에이전트 작업자용:** 필수 서브스킬: superpowers:subagent-driven-development(권장) 또는 superpowers:executing-plans를 사용하여 태스크별로 구현할 것. 체크박스(`- [ ]`) 형식으로 진행 추적.

**목표:** 현재 단순 일일 리포트를 5단계 테마 중심 파이프라인으로 교체하여, 시장 내러티브 기반 촉매 분석 리포트를 생성한다.

**아키텍처:** 5단계 파이프라인 (Ingest → Map → Shuffle → Catalyst → Synthesize). 각 단계는 `--stage` 플래그로 독립 실행 가능. 중간 결과는 `.cache/report/YYYY-MM-DD/`에 JSON으로 캐싱. LLM 호출은 LangSmith 트레이싱 태깅.

**기술 스택:** langchain-core, langchain-openai, langchain-anthropic, pydantic v2, typer, rich, yfinance, ddgs, httpx

**설계서:** `docs/superpowers/specs/2026-04-12-daily-report-v2-design.md`

---

## 파일 구조

```
src/
  llm/
    daily_report_models.py          # Pydantic 모델: IngestResult, IssueExtract, StockDetail, Theme, ShuffleResult, StockCatalyst, DailyReport
    prompts/
      __init__.py
      daily_report.py               # DailyReportPrompts 정적 메서드
    daily_report_analyzer.py        # LLM 호출 래퍼: map_chunk, merge_themes, find_catalysts, synthesize_report
  pipelines/
    report_stages/
      __init__.py                   # StageCache 캐시 로드/저장 헬퍼
      ingest.py                     # Stage 1: 병렬 데이터 수집
      map_issues.py                 # Stage 2: LLM Map (청크별 병렬 처리)
      shuffle_filter.py             # Stage 3: 테마 병합 + 티커 정규화 + 시장 데이터 보강
      catalyst.py                   # Stage 4: LLM Catalyst (tool calling으로 뉴스 검색)
      synthesize.py                 # Stage 5: LLM 최종 리포트 생성
    daily_report_v2.py              # 오케스트레이터: 단계 체이닝, --stage/--from 처리
  cli/
    main.py                         # 수정: report 커맨드를 V2 파이프라인으로 교체
themes.yaml                        # 알려진 테마 목록 (시드 파일)

tests/
  llm/
    test_daily_report_models.py
    test_daily_report_prompts.py
    test_daily_report_analyzer.py
  pipelines/
    report_stages/
      test_ingest.py
      test_map_issues.py
      test_shuffle_filter.py
      test_catalyst.py
      test_synthesize.py
    test_daily_report_v2.py
```

---

### Task 1: 데이터 모델

**파일:**
- 생성: `src/llm/daily_report_models.py`
- 테스트: `tests/llm/test_daily_report_models.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/llm/test_daily_report_models.py
import pytest
from src.llm.daily_report_models import (
    IngestResult,
    IssueExtract,
    StockDetail,
    Theme,
    ShuffleResult,
    StockCatalyst,
    DailyReport,
)


def test_ingest_result_creation():
    result = IngestResult(
        telegram_messages=[{"id": 1, "channel": "ch1", "text": "test", "timestamp": "2026-04-13T09:00:00"}],
        macro_snapshot={"vix": 18.2, "fear_greed": 62},
        market_news=[{"title": "SPY rises", "summary": "S&P 500 up 1%", "source": "yfinance", "url": "http://example.com"}],
        kr_flow=[{"ticker": "005930", "name": "삼성전자", "foreign_net": 500, "inst_net": 300}],
        momentum=[{"ticker": "NVDA", "price": 950.0, "change_pct": 5.8, "volume_ratio": 3.2}],
    )
    assert len(result.telegram_messages) == 1
    assert result.macro_snapshot["vix"] == 18.2


def test_issue_extract_creation():
    issue = IssueExtract(
        theme="CPO/광통신",
        tickers=["엔비디아", "LITE", "코위버"],
        sentiment="bull",
        summary="TSMC 실적 호조로 CPO 수요 확대 기대",
        source_ids=[101, 102],
    )
    assert issue.theme == "CPO/광통신"
    assert issue.sentiment == "bull"
    assert len(issue.tickers) == 3


def test_issue_extract_rejects_invalid_sentiment():
    with pytest.raises(Exception):
        IssueExtract(
            theme="test",
            tickers=[],
            sentiment="invalid",
            summary="test",
            source_ids=[],
        )


def test_stock_detail_optional_scores():
    stock = StockDetail(
        ticker="NVDA",
        market="US",
        mention_count=5,
        flow_score=None,
        volume_score=3.2,
        source="both",
        summaries=["NVDA 관련 요약"],
    )
    assert stock.flow_score is None
    assert stock.volume_score == 3.2


def test_theme_with_ticker_list():
    theme = Theme(
        name="CPO/광통신",
        narrative="TSMC 실적 발표로 CPO 수요 증가 기대",
        sentiment="bull",
        mention_count=15,
        stocks=["NVDA", "LITE", "코위버"],
    )
    assert theme.stocks == ["NVDA", "LITE", "코위버"]


def test_shuffle_result_stock_details_dict():
    detail = StockDetail(
        ticker="NVDA", market="US", mention_count=5,
        flow_score=None, volume_score=3.2, source="telegram",
        summaries=["summary1"],
    )
    theme = Theme(
        name="AI", narrative="AI boom", sentiment="bull",
        mention_count=10, stocks=["NVDA"],
    )
    result = ShuffleResult(themes=[theme], stock_details={"NVDA": detail})
    assert result.stock_details["NVDA"].ticker == "NVDA"


def test_stock_catalyst_multiple_themes():
    catalyst = StockCatalyst(
        ticker="NVDA",
        themes=["AI 반도체", "CPO/광통신"],
        news=["NVDA announces new chip"],
        catalyst_summary="차세대 칩 발표로 AI 인프라 수요 견인",
    )
    assert len(catalyst.themes) == 2


def test_daily_report_creation():
    report = DailyReport(
        date="2026-04-13",
        market_pulse="VIX 18.2 | F&G 62 | 리스크온 환경 지속",
        narrative_and_themes="오늘 시장의 핵심은 AI 인프라...",
        featured_analysis="[CPO/광통신]\n- 코위버: 외인 순매수 +30억",
    )
    assert report.date == "2026-04-13"


def test_models_json_roundtrip():
    """모든 모델은 캐시 저장을 위해 JSON 직렬화/역직렬화가 가능해야 한다."""
    theme = Theme(
        name="AI", narrative="AI boom", sentiment="bull",
        mention_count=10, stocks=["NVDA"],
    )
    detail = StockDetail(
        ticker="NVDA", market="US", mention_count=5,
        flow_score=None, volume_score=3.2, source="telegram",
        summaries=["summary1"],
    )
    result = ShuffleResult(themes=[theme], stock_details={"NVDA": detail})
    json_str = result.model_dump_json()
    restored = ShuffleResult.model_validate_json(json_str)
    assert restored.themes[0].name == "AI"
    assert restored.stock_details["NVDA"].volume_score == 3.2
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/llm/test_daily_report_models.py -v`
예상: `ModuleNotFoundError: No module named 'src.llm.daily_report_models'`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# src/llm/daily_report_models.py
from __future__ import annotations

from pydantic import BaseModel
from typing import Literal


class IngestResult(BaseModel):
    telegram_messages: list[dict]
    macro_snapshot: dict
    market_news: list[dict]
    kr_flow: list[dict]
    momentum: list[dict]


class IssueExtract(BaseModel):
    theme: str
    tickers: list[str]
    sentiment: Literal["bull", "bear", "neutral"]
    summary: str
    source_ids: list[int]


class StockDetail(BaseModel):
    ticker: str
    market: Literal["KR", "US"]
    mention_count: int
    flow_score: float | None
    volume_score: float | None
    source: Literal["telegram", "market_data", "both"]
    summaries: list[str]


class Theme(BaseModel):
    name: str
    narrative: str
    sentiment: Literal["bull", "bear", "neutral"]
    mention_count: int
    stocks: list[str]


class ShuffleResult(BaseModel):
    themes: list[Theme]
    stock_details: dict[str, StockDetail]


class StockCatalyst(BaseModel):
    ticker: str
    themes: list[str]
    news: list[str]
    catalyst_summary: str


class DailyReport(BaseModel):
    date: str
    market_pulse: str
    narrative_and_themes: str
    featured_analysis: str
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/llm/test_daily_report_models.py -v`
예상: 9개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/llm/daily_report_models.py tests/llm/test_daily_report_models.py
git commit -m "feat: add daily report V2 pydantic data models"
```

---

### Task 2: 프롬프트 클래스

**파일:**
- 생성: `src/llm/prompts/__init__.py`
- 생성: `src/llm/prompts/daily_report.py`
- 테스트: `tests/llm/test_daily_report_prompts.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/llm/test_daily_report_prompts.py
from src.llm.prompts.daily_report import DailyReportPrompts


def test_map_issues_prompt_includes_themes_and_messages():
    prompt = DailyReportPrompts.map_issues(
        known_themes="CPO/광통신\nAI 반도체",
        messages="[101] 엔비디아 실적 호조",
    )
    assert "CPO/광통신" in prompt
    assert "AI 반도체" in prompt
    assert "[101] 엔비디아 실적 호조" in prompt
    assert "theme" in prompt
    assert "tickers" in prompt
    assert "sentiment" in prompt


def test_merge_themes_prompt_includes_both_lists():
    prompt = DailyReportPrompts.merge_themes(
        known_themes="CPO/광통신\nAI 반도체",
        new_themes="광통신\nco-packaged optics\n방산",
    )
    assert "CPO/광통신" in prompt
    assert "co-packaged optics" in prompt
    assert "매핑" in prompt


def test_catalyst_prompt_includes_themes_json():
    prompt = DailyReportPrompts.catalyst(
        themes_json='[{"name": "CPO/광통신", "stocks": ["LITE", "COHR"]}]',
    )
    assert "LITE" in prompt
    assert "NewsTool" in prompt


def test_synthesize_prompt_includes_all_sections():
    prompt = DailyReportPrompts.synthesize(
        macro="VIX 18.2",
        news="SPY rises 1%",
        themes="CPO/광통신: bull",
        catalysts="LITE: 실적 호조",
    )
    assert "VIX 18.2" in prompt
    assert "SPY rises 1%" in prompt
    assert "CPO/광통신" in prompt
    assert "LITE" in prompt
    assert "10줄 이내" in prompt
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/llm/test_daily_report_prompts.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# src/llm/prompts/__init__.py
```

```python
# src/llm/prompts/daily_report.py
from __future__ import annotations


class DailyReportPrompts:
    @staticmethod
    def map_issues(known_themes: str, messages: str) -> str:
        """Stage 2: 텔레그램 메시지에서 테마/종목/감성 추출"""
        return f"""아래 텔레그램 메시지들에서 투자 관련 이슈를 추출하세요.
각 이슈에 대해:
- theme: 투자 테마명. 아래 기존 테마 목록에 해당하면 그대로 사용하고,
         해당하지 않으면 새 테마명을 자유 생성하세요.
- tickers: 언급된 종목명 (원문 그대로, 정규화하지 않음)
- sentiment: 시장 영향 방향 (bull/bear/neutral)
- summary: 핵심 내용 요약 (1-2문장)
- source_ids: 해당 메시지 ID 목록

기존 테마 목록:
{known_themes}

잡담, 광고, 투자와 무관한 메시지는 무시하세요.
한 메시지가 여러 테마를 다루면 각각 별도로 분리하세요.

메시지:
{messages}"""

    @staticmethod
    def merge_themes(known_themes: str, new_themes: str) -> str:
        """Stage 3 Step 1: 유사 테마 병합"""
        return f"""아래에 기존 테마 목록과 새로 추출된 테마 목록이 있습니다.
새 테마 중 기존 테마와 동일하거나 유사한 것은 기존 테마명으로 매핑하고,
완전히 새로운 테마는 그대로 유지하세요.

기존 테마 목록:
{known_themes}

새로 추출된 테마:
{new_themes}

출력: {{"매핑": {{"원래 테마명": "정규화된 테마명", ...}}}}"""

    @staticmethod
    def catalyst(themes_json: str) -> str:
        """Stage 4: 주도주별 촉매 뉴스 검색"""
        return f"""아래 테마별 주도주 목록이 주어집니다.
각 종목에 대해 NewsTool로 최근 뉴스를 검색하고,
해당 종목이 주목받는 촉매(catalyst)를 파악하세요.

테마당 상위 2-3개 종목에 집중하세요.
뉴스가 없는 종목은 텔레그램 원문 요약을 촉매로 사용하세요.

테마 및 주도주:
{themes_json}"""

    @staticmethod
    def synthesize(macro: str, news: str, themes: str, catalysts: str) -> str:
        """Stage 5: 전체 통합 리포트 생성"""
        return f"""아래 데이터를 기반으로 일일 시장 리포트를 작성하세요.

3개 섹션으로 구성:
1. 시장 온도 (10줄 이내): 매크로 수치 해석 + 시장 분위기 판단
2. 시장 내러티브 & 주목 테마: 흐름 스토리 + 테마 간 연결고리
3. 주도주 분석: 테마별 핵심 종목 + 촉매 + 수급/거래량 근거

매크로:
{macro}

시장 뉴스:
{news}

테마 분석:
{themes}

촉매 분석:
{catalysts}"""
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/llm/test_daily_report_prompts.py -v`
예상: 4개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/llm/prompts/__init__.py src/llm/prompts/daily_report.py tests/llm/test_daily_report_prompts.py
git commit -m "feat: add DailyReportPrompts static method class"
```

---

### Task 3: 스테이지 인프라 (캐시 + 러너)

**파일:**
- 생성: `src/pipelines/report_stages/__init__.py`
- 테스트: `tests/pipelines/report_stages/__init__.py` (빈 파일)
- 테스트: `tests/pipelines/report_stages/test_stage_infra.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/pipelines/report_stages/test_stage_infra.py
import json
import pytest
from pathlib import Path
from src.pipelines.report_stages import StageCache


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / ".cache" / "report" / "2026-04-13"


def test_save_and_load_stage_result(cache_dir):
    cache = StageCache(cache_dir)
    data = {"themes": [{"name": "AI", "stocks": ["NVDA"]}]}
    cache.save("3_shuffle", data)

    loaded = cache.load("3_shuffle")
    assert loaded["themes"][0]["name"] == "AI"


def test_load_missing_stage_raises(cache_dir):
    cache = StageCache(cache_dir)
    with pytest.raises(FileNotFoundError):
        cache.load("2_map")


def test_has_stage(cache_dir):
    cache = StageCache(cache_dir)
    assert not cache.has("1_ingest")
    cache.save("1_ingest", {"data": True})
    assert cache.has("1_ingest")


def test_cache_dir_auto_created(tmp_path):
    cache_dir = tmp_path / "deep" / "nested" / "dir"
    cache = StageCache(cache_dir)
    cache.save("test", {"ok": True})
    assert cache.load("test") == {"ok": True}


def test_get_cache_dir_for_date():
    base = Path(".cache/report")
    result = StageCache.cache_dir_for_date(base, "2026-04-13")
    assert result == base / "2026-04-13"
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_stage_infra.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# tests/pipelines/report_stages/__init__.py
```

```python
# src/pipelines/report_stages/__init__.py
from __future__ import annotations

import json
from pathlib import Path


class StageCache:
    """파이프라인 스테이지 중간 결과를 JSON으로 관리하는 캐시."""

    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir

    @staticmethod
    def cache_dir_for_date(base: Path, date_str: str) -> Path:
        return base / date_str

    def save(self, stage_name: str, data: dict) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{stage_name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load(self, stage_name: str) -> dict:
        path = self._dir / f"{stage_name}.json"
        if not path.exists():
            raise FileNotFoundError(f"스테이지 캐시를 찾을 수 없습니다: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def has(self, stage_name: str) -> bool:
        return (self._dir / f"{stage_name}.json").exists()
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_stage_infra.py -v`
예상: 5개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/pipelines/report_stages/__init__.py tests/pipelines/report_stages/__init__.py tests/pipelines/report_stages/test_stage_infra.py
git commit -m "feat: add StageCache for pipeline intermediate result storage"
```

---

### Task 4: themes.yaml 시드 파일 + 로더

**파일:**
- 생성: `themes.yaml`
- 생성: `src/pipelines/report_stages/theme_config.py`
- 테스트: `tests/pipelines/report_stages/test_theme_config.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/pipelines/report_stages/test_theme_config.py
import pytest
from pathlib import Path
from src.pipelines.report_stages.theme_config import ThemeConfig


@pytest.fixture
def theme_file(tmp_path):
    path = tmp_path / "themes.yaml"
    path.write_text(
        "themes:\n  - CPO/광통신\n  - AI 반도체\n  - 방산\n",
        encoding="utf-8",
    )
    return path


def test_load_known_themes(theme_file):
    config = ThemeConfig(theme_file)
    themes = config.load()
    assert "CPO/광통신" in themes
    assert "AI 반도체" in themes
    assert len(themes) == 3


def test_add_new_themes(theme_file):
    config = ThemeConfig(theme_file)
    config.add_themes(["로봇/자동화", "양자컴퓨팅"])
    themes = config.load()
    assert "로봇/자동화" in themes
    assert "양자컴퓨팅" in themes
    assert len(themes) == 5


def test_add_duplicate_themes_ignored(theme_file):
    config = ThemeConfig(theme_file)
    config.add_themes(["CPO/광통신", "새테마"])
    themes = config.load()
    assert themes.count("CPO/광통신") == 1
    assert len(themes) == 4


def test_as_prompt_string(theme_file):
    config = ThemeConfig(theme_file)
    prompt_str = config.as_prompt_string()
    assert "- CPO/광통신" in prompt_str
    assert "- AI 반도체" in prompt_str


def test_missing_file_returns_empty():
    config = ThemeConfig(Path("/nonexistent/themes.yaml"))
    themes = config.load()
    assert themes == []
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_theme_config.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```yaml
# themes.yaml
themes:
  - CPO/광통신
  - AI 반도체
  - 방산/우주항공
  - 2차전지/배터리
  - 바이오/제약
  - 로봇/자동화
  - 원전/에너지
  - 반도체 장비
  - 데이터센터
  - 전력기기
  - 조선/해운
  - 자율주행
  - XR/메타버스
  - 사이버보안
  - 금융/핀테크
```

```python
# src/pipelines/report_stages/theme_config.py
from __future__ import annotations

from pathlib import Path

import yaml


class ThemeConfig:
    """themes.yaml에서 알려진 테마 목록을 로드/업데이트한다."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[str]:
        if not self._path.exists():
            return []
        data = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        return data.get("themes", []) if data else []

    def add_themes(self, new_themes: list[str]) -> None:
        existing = self.load()
        existing_set = set(existing)
        for theme in new_themes:
            if theme not in existing_set:
                existing.append(theme)
                existing_set.add(theme)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            yaml.dump({"themes": existing}, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    def as_prompt_string(self) -> str:
        themes = self.load()
        return "\n".join(f"- {t}" for t in themes)
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_theme_config.py -v`
예상: 5개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add themes.yaml src/pipelines/report_stages/theme_config.py tests/pipelines/report_stages/test_theme_config.py
git commit -m "feat: add themes.yaml and ThemeConfig loader"
```

---

### Task 5: Stage 1 — Ingest (병렬 수집)

**파일:**
- 생성: `src/pipelines/report_stages/ingest.py`
- 테스트: `tests/pipelines/report_stages/test_ingest.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/pipelines/report_stages/test_ingest.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.pipelines.report_stages.ingest import IngestStage
from src.llm.daily_report_models import IngestResult


@pytest.fixture
def mock_macro_tool():
    tool = AsyncMock()
    tool.execute.return_value = MagicMock(
        success=True,
        data=MagicMock(
            vix=18.2, vix_change=1.3, fear_greed=62, fear_greed_label="Greed",
            wti=78.5, wti_change=1.2, us_10y=4.32, us_2y=3.87,
            yield_spread=0.45, dxy=104.2, dxy_change=-0.3,
        ),
    )
    return tool


@pytest.fixture
def mock_news_tool():
    tool = AsyncMock()
    tool.execute.return_value = MagicMock(
        success=True,
        data=[
            MagicMock(title="SPY rises", summary="S&P 500 up 1%", url="http://example.com"),
        ],
    )
    return tool


@pytest.fixture
def mock_kis_provider():
    provider = AsyncMock()
    provider.get_investor_ranking.return_value = [
        {"ticker": "005930", "name": "삼성전자", "net_buy_volume": 500, "net_buy_amount": 30000},
    ]
    provider.get_us_ranking_updown.return_value = [
        {"ticker": "NVDA", "name": "NVIDIA", "change_pct": 5.8, "price": 950, "volume": 100000, "exchange": "NAS"},
    ]
    provider.get_us_ranking_volume.return_value = [
        {"ticker": "NVDA", "name": "NVIDIA", "price": 950, "volume": 200000, "exchange": "NAS"},
    ]
    return provider


@pytest.fixture
def mock_telegram_loader():
    loader = MagicMock()
    loader.load.return_value = [
        {"id": 1, "channel": "ch1", "text": "엔비디아 실적 호조", "timestamp": "2026-04-13T09:00:00"},
    ]
    return loader


@pytest.mark.asyncio
async def test_ingest_stage_returns_ingest_result(
    mock_macro_tool, mock_news_tool, mock_kis_provider, mock_telegram_loader
):
    stage = IngestStage(
        macro_tool=mock_macro_tool,
        news_tool=mock_news_tool,
        kis_provider=mock_kis_provider,
        telegram_loader=mock_telegram_loader,
    )
    result = await stage.run()

    assert isinstance(result, IngestResult)
    assert len(result.telegram_messages) == 1
    assert result.macro_snapshot["vix"] == 18.2
    assert len(result.market_news) >= 1
    assert len(result.kr_flow) >= 1
    assert len(result.momentum) >= 1


@pytest.mark.asyncio
async def test_ingest_stage_handles_kis_failure(
    mock_macro_tool, mock_news_tool, mock_telegram_loader
):
    mock_kis = AsyncMock()
    mock_kis.get_investor_ranking.side_effect = Exception("KIS API down")
    mock_kis.get_us_ranking_updown.side_effect = Exception("KIS API down")
    mock_kis.get_us_ranking_volume.side_effect = Exception("KIS API down")

    stage = IngestStage(
        macro_tool=mock_macro_tool,
        news_tool=mock_news_tool,
        kis_provider=mock_kis,
        telegram_loader=mock_telegram_loader,
    )
    result = await stage.run()

    assert isinstance(result, IngestResult)
    assert result.kr_flow == []
    assert result.momentum == []
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_ingest.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# src/pipelines/report_stages/ingest.py
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from src.llm.daily_report_models import IngestResult
from src.tools.macro import MacroTool
from src.tools.news import NewsTool

logger = logging.getLogger(__name__)

# 시장 뉴스 검색 키워드
MARKET_NEWS_QUERIES = ["SPY", "QQQ", "KOSPI", "나스닥", "S&P 500"]


@dataclass
class IngestStage:
    macro_tool: MacroTool
    news_tool: NewsTool
    kis_provider: Any  # KISProvider (선택적 의존성)
    telegram_loader: Any  # TelegramLoader

    async def run(self) -> IngestResult:
        telegram_task = asyncio.to_thread(self.telegram_loader.load)
        macro_task = self._fetch_macro()
        news_task = self._fetch_market_news()
        kr_flow_task = self._fetch_kr_flow()
        momentum_task = self._fetch_momentum()

        results = await asyncio.gather(
            telegram_task, macro_task, news_task, kr_flow_task, momentum_task,
            return_exceptions=True,
        )

        telegram_messages = results[0] if not isinstance(results[0], Exception) else []
        macro_snapshot = results[1] if not isinstance(results[1], Exception) else {}
        market_news = results[2] if not isinstance(results[2], Exception) else []
        kr_flow = results[3] if not isinstance(results[3], Exception) else []
        momentum = results[4] if not isinstance(results[4], Exception) else []

        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.warning("수집 소스 %d 실패: %s", i, r)

        return IngestResult(
            telegram_messages=telegram_messages,
            macro_snapshot=macro_snapshot,
            market_news=market_news,
            kr_flow=kr_flow,
            momentum=momentum,
        )

    async def _fetch_macro(self) -> dict:
        result = await self.macro_tool.execute()
        if not result.success:
            return {}
        snap = result.data
        return {
            "vix": snap.vix, "vix_change": snap.vix_change,
            "fear_greed": snap.fear_greed, "fear_greed_label": snap.fear_greed_label,
            "wti": snap.wti, "wti_change": snap.wti_change,
            "us_10y": snap.us_10y, "us_2y": snap.us_2y,
            "yield_spread": snap.yield_spread,
            "dxy": snap.dxy, "dxy_change": snap.dxy_change,
        }

    async def _fetch_market_news(self) -> list[dict]:
        all_news: list[dict] = []
        for query in MARKET_NEWS_QUERIES:
            try:
                result = await self.news_tool.execute(ticker=query, limit=5)
                if result.success and result.data:
                    for article in result.data:
                        all_news.append({
                            "title": article.title,
                            "summary": article.summary,
                            "source": query,
                            "url": article.url,
                        })
            except Exception as e:
                logger.warning("%s 뉴스 수집 실패: %s", query, e)
        return all_news

    async def _fetch_kr_flow(self) -> list[dict]:
        try:
            foreign = await self.kis_provider.get_investor_ranking(
                investor_type="foreign", top_n=30,
            )
            institution = await self.kis_provider.get_investor_ranking(
                investor_type="institution", top_n=30,
            )
            merged: dict[str, dict] = {}
            for item in foreign:
                merged[item["ticker"]] = {
                    "ticker": item["ticker"],
                    "name": item["name"],
                    "foreign_net": item.get("net_buy_amount", 0),
                    "inst_net": 0,
                }
            for item in institution:
                key = item["ticker"]
                if key in merged:
                    merged[key]["inst_net"] = item.get("net_buy_amount", 0)
                else:
                    merged[key] = {
                        "ticker": key,
                        "name": item["name"],
                        "foreign_net": 0,
                        "inst_net": item.get("net_buy_amount", 0),
                    }
            return list(merged.values())
        except Exception as e:
            logger.warning("KR 수급 수집 실패: %s", e)
            return []

    async def _fetch_momentum(self) -> list[dict]:
        try:
            results: list[dict] = []
            seen: set[str] = set()
            for exchange in ("NAS", "NYS"):
                updown = await self.kis_provider.get_us_ranking_updown(
                    exchange=exchange, direction="up", top_n=30,
                )
                for item in updown:
                    if item["ticker"] not in seen:
                        results.append({
                            "ticker": item["ticker"],
                            "name": item.get("name", ""),
                            "price": item.get("price", 0),
                            "change_pct": item.get("change_pct", 0),
                            "volume_ratio": 0,
                            "exchange": item.get("exchange", exchange),
                        })
                        seen.add(item["ticker"])
                volume = await self.kis_provider.get_us_ranking_volume(
                    exchange=exchange, top_n=30,
                )
                for item in volume:
                    if item["ticker"] not in seen:
                        results.append({
                            "ticker": item["ticker"],
                            "name": item.get("name", ""),
                            "price": item.get("price", 0),
                            "change_pct": 0,
                            "volume_ratio": 0,
                            "exchange": item.get("exchange", exchange),
                        })
                        seen.add(item["ticker"])
            return results
        except Exception as e:
            logger.warning("US 모멘텀 수집 실패: %s", e)
            return []
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_ingest.py -v`
예상: 2개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/pipelines/report_stages/ingest.py tests/pipelines/report_stages/test_ingest.py
git commit -m "feat: add Stage 1 IngestStage with parallel data collection"
```

---

### Task 6: Stage 2 — LLM Map

**파일:**
- 생성: `src/llm/daily_report_analyzer.py`
- 생성: `src/pipelines/report_stages/map_issues.py`
- 테스트: `tests/pipelines/report_stages/test_map_issues.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/pipelines/report_stages/test_map_issues.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.pipelines.report_stages.map_issues import MapStage
from src.llm.daily_report_models import IssueExtract


@pytest.fixture
def sample_messages():
    return [
        {"id": i, "channel": "ch1", "text": f"메시지 {i}", "timestamp": "2026-04-13T09:00:00"}
        for i in range(120)
    ]


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=[
        IssueExtract(
            theme="CPO/광통신",
            tickers=["엔비디아", "LITE"],
            sentiment="bull",
            summary="CPO 수요 증가",
            source_ids=[1, 2],
        ),
    ])
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.asyncio
async def test_map_stage_chunks_messages(sample_messages, mock_llm):
    stage = MapStage(llm=mock_llm, known_themes="CPO/광통신\nAI 반도체", chunk_size=50)
    issues = await stage.run(sample_messages)

    assert len(issues) >= 1
    assert all(isinstance(i, IssueExtract) for i in issues)
    # 120개 메시지 / 50 청크 크기 = 3개 청크 → 3번 LLM 호출
    assert mock_llm.with_structured_output.return_value.ainvoke.call_count == 3


@pytest.mark.asyncio
async def test_map_stage_empty_messages(mock_llm):
    stage = MapStage(llm=mock_llm, known_themes="", chunk_size=50)
    issues = await stage.run([])
    assert issues == []


@pytest.mark.asyncio
async def test_map_stage_handles_chunk_failure(sample_messages, mock_llm):
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise Exception("LLM timeout")
        return [
            IssueExtract(
                theme="AI", tickers=["NVDA"], sentiment="bull",
                summary="AI boom", source_ids=[1],
            ),
        ]

    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(side_effect=side_effect)
    stage = MapStage(llm=mock_llm, known_themes="", chunk_size=50)
    issues = await stage.run(sample_messages)

    # 3개 청크 중 1개 실패 → 성공한 2개 청크의 결과만
    assert len(issues) == 2
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_map_issues.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: LLM 분석기 래퍼 작성**

```python
# src/llm/daily_report_analyzer.py
from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel

from src.llm.daily_report_models import IssueExtract, StockCatalyst, DailyReport
from src.llm.prompts.daily_report import DailyReportPrompts

logger = logging.getLogger(__name__)


async def map_chunk(
    llm: BaseChatModel,
    known_themes: str,
    messages_text: str,
    run_name: str = "map_chunk",
    metadata: dict | None = None,
) -> list[IssueExtract]:
    """단일 메시지 청크에서 이슈를 추출한다."""
    structured_llm = llm.with_structured_output(list[IssueExtract])
    prompt = DailyReportPrompts.map_issues(known_themes, messages_text)
    result = await structured_llm.ainvoke(
        prompt,
        config={"run_name": run_name, "metadata": metadata or {}},
    )
    return result


async def merge_themes_llm(
    llm: BaseChatModel,
    known_themes: str,
    new_themes: str,
) -> dict[str, str]:
    """유사 테마를 LLM으로 병합한다."""
    prompt = DailyReportPrompts.merge_themes(known_themes, new_themes)
    structured_llm = llm.with_structured_output(dict)
    result = await structured_llm.ainvoke(
        prompt,
        config={"run_name": "merge_themes"},
    )
    return result.get("매핑", {})


async def synthesize_report(
    llm: BaseChatModel,
    macro: str,
    news: str,
    themes: str,
    catalysts: str,
    metadata: dict | None = None,
) -> DailyReport:
    """전체 데이터를 통합하여 최종 리포트를 생성한다."""
    structured_llm = llm.with_structured_output(DailyReport)
    prompt = DailyReportPrompts.synthesize(macro, news, themes, catalysts)
    result = await structured_llm.ainvoke(
        prompt,
        config={"run_name": "synthesize_final", "metadata": metadata or {}},
    )
    return result
```

- [ ] **Step 4: MapStage 구현 작성**

```python
# src/pipelines/report_stages/map_issues.py
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from src.llm.daily_report_models import IssueExtract
from src.llm.daily_report_analyzer import map_chunk

logger = logging.getLogger(__name__)


def _format_messages_for_prompt(messages: list[dict]) -> str:
    """메시지 목록을 프롬프트용 텍스트로 변환한다."""
    lines = []
    for msg in messages:
        msg_id = msg.get("id", "?")
        channel = msg.get("channel", "?")
        text = msg.get("text", "")
        lines.append(f"[{msg_id}] ({channel}) {text}")
    return "\n".join(lines)


@dataclass
class MapStage:
    llm: BaseChatModel
    known_themes: str
    chunk_size: int = 50

    async def run(self, messages: list[dict]) -> list[IssueExtract]:
        if not messages:
            return []

        chunks = [
            messages[i : i + self.chunk_size]
            for i in range(0, len(messages), self.chunk_size)
        ]

        tasks = [
            self._process_chunk(chunk, idx)
            for idx, chunk in enumerate(chunks)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_issues: list[IssueExtract] = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning("Map 청크 %d 실패: %s", idx, result)
                continue
            all_issues.extend(result)
        return all_issues

    async def _process_chunk(
        self, chunk: list[dict], chunk_index: int
    ) -> list[IssueExtract]:
        messages_text = _format_messages_for_prompt(chunk)
        return await map_chunk(
            llm=self.llm,
            known_themes=self.known_themes,
            messages_text=messages_text,
            run_name=f"map_chunk_{chunk_index}",
            metadata={"stage": "map", "chunk_index": chunk_index, "chunk_size": len(chunk)},
        )
```

- [ ] **Step 5: 테스트 통과 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_map_issues.py -v`
예상: 3개 테스트 모두 PASS

- [ ] **Step 6: 커밋**

```bash
git add src/llm/daily_report_analyzer.py src/pipelines/report_stages/map_issues.py tests/pipelines/report_stages/test_map_issues.py
git commit -m "feat: add Stage 2 MapStage with chunked parallel LLM extraction"
```

---

### Task 7: Stage 3 — Shuffle & Filter

**파일:**
- 생성: `src/pipelines/report_stages/shuffle_filter.py`
- 테스트: `tests/pipelines/report_stages/test_shuffle_filter.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/pipelines/report_stages/test_shuffle_filter.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.pipelines.report_stages.shuffle_filter import ShuffleStage
from src.llm.daily_report_models import IssueExtract, ShuffleResult


@pytest.fixture
def sample_issues():
    return [
        IssueExtract(theme="CPO/광통신", tickers=["엔비디아", "LITE"], sentiment="bull",
                     summary="CPO 수요 증가", source_ids=[1]),
        IssueExtract(theme="CPO/광통신", tickers=["코위버", "LITE"], sentiment="bull",
                     summary="광트랜시버 수주", source_ids=[2]),
        IssueExtract(theme="AI 반도체", tickers=["엔비디아", "SK하이닉스"], sentiment="bull",
                     summary="AI 칩 수요 폭발", source_ids=[3]),
        IssueExtract(theme="방산", tickers=["한화에어로스페이스"], sentiment="neutral",
                     summary="방산 수출 계약", source_ids=[4]),
    ]


@pytest.fixture
def sample_kr_flow():
    return [
        {"ticker": "005930", "name": "삼성전자", "foreign_net": 500, "inst_net": 300},
        {"ticker": "A058400", "name": "코위버", "foreign_net": 200, "inst_net": 150},
    ]


@pytest.fixture
def sample_momentum():
    return [
        {"ticker": "NVDA", "name": "NVIDIA", "price": 950, "change_pct": 5.8, "volume_ratio": 3.2},
        {"ticker": "LITE", "name": "Lumentum", "price": 85, "change_pct": 3.5, "volume_ratio": 2.1},
    ]


@pytest.fixture
def mock_ticker_resolver():
    resolver = AsyncMock()

    async def resolve(query):
        mapping = {
            "엔비디아": MagicMock(resolved_ticker="NVDA"),
            "LITE": MagicMock(resolved_ticker="LITE"),
            "코위버": MagicMock(resolved_ticker="A058400"),
            "SK하이닉스": MagicMock(resolved_ticker="000660"),
            "한화에어로스페이스": MagicMock(resolved_ticker="012450"),
        }
        return mapping.get(query, MagicMock(resolved_ticker=query))

    resolver.resolve = AsyncMock(side_effect=resolve)
    return resolver


@pytest.fixture
def mock_merge_llm():
    llm = MagicMock()
    structured = MagicMock()
    # 병합 불필요 — 모든 테마가 이미 정규화됨
    structured.ainvoke = AsyncMock(return_value={"매핑": {}})
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.asyncio
async def test_shuffle_produces_themes_sorted_by_mention(
    sample_issues, sample_kr_flow, sample_momentum,
    mock_ticker_resolver, mock_merge_llm,
):
    stage = ShuffleStage(
        ticker_resolver=mock_ticker_resolver,
        merge_llm=mock_merge_llm,
        known_themes=["CPO/광통신", "AI 반도체", "방산"],
        top_n=5,
    )
    result = await stage.run(sample_issues, sample_kr_flow, sample_momentum)

    assert isinstance(result, ShuffleResult)
    # CPO 2회 언급, AI 1회, 방산 1회 → CPO가 첫 번째
    assert result.themes[0].name == "CPO/광통신"
    assert result.themes[0].mention_count == 2


@pytest.mark.asyncio
async def test_shuffle_enriches_stock_details_with_flow(
    sample_issues, sample_kr_flow, sample_momentum,
    mock_ticker_resolver, mock_merge_llm,
):
    stage = ShuffleStage(
        ticker_resolver=mock_ticker_resolver,
        merge_llm=mock_merge_llm,
        known_themes=["CPO/광통신", "AI 반도체", "방산"],
        top_n=5,
    )
    result = await stage.run(sample_issues, sample_kr_flow, sample_momentum)

    # 코위버는 kr_flow에서 flow_score를 받아야 함
    if "A058400" in result.stock_details:
        assert result.stock_details["A058400"].flow_score is not None


@pytest.mark.asyncio
async def test_shuffle_enriches_stock_details_with_momentum(
    sample_issues, sample_kr_flow, sample_momentum,
    mock_ticker_resolver, mock_merge_llm,
):
    stage = ShuffleStage(
        ticker_resolver=mock_ticker_resolver,
        merge_llm=mock_merge_llm,
        known_themes=["CPO/광통신", "AI 반도체", "방산"],
        top_n=5,
    )
    result = await stage.run(sample_issues, sample_kr_flow, sample_momentum)

    # NVDA는 momentum에서 volume_score를 받아야 함
    if "NVDA" in result.stock_details:
        assert result.stock_details["NVDA"].volume_score is not None


@pytest.mark.asyncio
async def test_shuffle_collects_summaries_per_stock(
    sample_issues, sample_kr_flow, sample_momentum,
    mock_ticker_resolver, mock_merge_llm,
):
    stage = ShuffleStage(
        ticker_resolver=mock_ticker_resolver,
        merge_llm=mock_merge_llm,
        known_themes=["CPO/광통신", "AI 반도체", "방산"],
        top_n=5,
    )
    result = await stage.run(sample_issues, sample_kr_flow, sample_momentum)

    # NVDA는 2개 이슈에 등장 → 2개 요약이 있어야 함
    nvda = result.stock_details.get("NVDA")
    if nvda:
        assert len(nvda.summaries) == 2
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_shuffle_filter.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# src/pipelines/report_stages/shuffle_filter.py
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel

from src.llm.daily_report_models import (
    IssueExtract,
    ShuffleResult,
    StockDetail,
    Theme,
)
from src.llm.daily_report_analyzer import merge_themes_llm

logger = logging.getLogger(__name__)


def _detect_market(ticker: str) -> str:
    """한국 티커 감지 (6자리 숫자 또는 A+6자리 숫자)"""
    # 순수 6자리 숫자: 005930 (삼성전자)
    if ticker.isdigit() and len(ticker) == 6:
        return "KR"
    # A + 6자리 숫자: A058400 (코위버) - 총 7글자
    if len(ticker) == 7 and ticker.startswith("A") and ticker[1:].isdigit():
        return "KR"
    return "US"


@dataclass
class ShuffleStage:
    ticker_resolver: object  # TickerResolver
    merge_llm: BaseChatModel
    known_themes: list[str]
    top_n: int = 7

    async def run(
        self,
        issues: list[IssueExtract],
        kr_flow: list[dict],
        momentum: list[dict],
    ) -> ShuffleResult:
        # Step 1: 유사 테마 LLM으로 병합
        raw_theme_names = list({issue.theme for issue in issues})
        new_themes = [t for t in raw_theme_names if t not in self.known_themes]
        theme_mapping: dict[str, str] = {}
        if new_themes:
            known_str = "\n".join(f"- {t}" for t in self.known_themes)
            new_str = "\n".join(f"- {t}" for t in new_themes)
            theme_mapping = await merge_themes_llm(self.merge_llm, known_str, new_str)

        # Step 2: 티커 정규화 + 테마별 그룹핑
        all_raw_tickers: set[str] = set()
        for issue in issues:
            all_raw_tickers.update(issue.tickers)

        ticker_map: dict[str, str] = {}
        for raw in all_raw_tickers:
            try:
                resolution = await self.ticker_resolver.resolve(raw)
                ticker_map[raw] = resolution.resolved_ticker
            except Exception as e:
                logger.warning("티커 변환 실패 %s: %s", raw, e)
                ticker_map[raw] = raw

        # 정규화된 테마별 그룹핑
        theme_issues: dict[str, list[IssueExtract]] = defaultdict(list)
        for issue in issues:
            normalized = theme_mapping.get(issue.theme, issue.theme)
            theme_issues[normalized].append(issue)

        # 종목별 상세 정보 수집
        stock_details: dict[str, dict] = defaultdict(lambda: {
            "mention_count": 0, "summaries": [], "source": "telegram",
        })
        for theme_name, theme_issue_list in theme_issues.items():
            for issue in theme_issue_list:
                for raw_ticker in issue.tickers:
                    resolved = ticker_map.get(raw_ticker, raw_ticker)
                    stock_details[resolved]["mention_count"] += 1
                    stock_details[resolved]["summaries"].append(issue.summary)

        # 테마 모델 구성
        themes: list[Theme] = []
        for theme_name, theme_issue_list in theme_issues.items():
            sentiment_counts = Counter(i.sentiment for i in theme_issue_list)
            dominant_sentiment = sentiment_counts.most_common(1)[0][0]

            theme_tickers: dict[str, int] = Counter()
            for issue in theme_issue_list:
                for raw_ticker in issue.tickers:
                    resolved = ticker_map.get(raw_ticker, raw_ticker)
                    theme_tickers[resolved] += 1

            sorted_tickers = [t for t, _ in theme_tickers.most_common()]
            summaries = [i.summary for i in theme_issue_list]
            narrative = summaries[0] if summaries else ""

            themes.append(Theme(
                name=theme_name,
                narrative=narrative,
                sentiment=dominant_sentiment,
                mention_count=len(theme_issue_list),
                stocks=sorted_tickers,
            ))

        # Step 3: 시장 데이터로 보강
        kr_flow_map = {item["ticker"]: item for item in kr_flow}
        momentum_map = {item["ticker"]: item for item in momentum}

        final_details: dict[str, StockDetail] = {}
        all_tickers = set(stock_details.keys())

        for ticker in all_tickers:
            info = stock_details[ticker]
            market = _detect_market(ticker)
            flow_score = None
            volume_score = None
            source = "telegram"

            if ticker in kr_flow_map:
                flow_data = kr_flow_map[ticker]
                flow_score = float(flow_data.get("foreign_net", 0)) + float(flow_data.get("inst_net", 0))
                source = "both"

            if ticker in momentum_map:
                mom_data = momentum_map[ticker]
                volume_score = float(mom_data.get("change_pct", 0)) + float(mom_data.get("volume_ratio", 0))
                source = "both"

            final_details[ticker] = StockDetail(
                ticker=ticker,
                market=market,
                mention_count=info["mention_count"],
                flow_score=flow_score,
                volume_score=volume_score,
                source=source,
                summaries=info["summaries"],
            )

        # 수급/거래량 상위이지만 테마에 없는 종목 → "기타 수급 특징주" 테마에 편입
        market_only_tickers: list[str] = []
        for ticker in set(kr_flow_map.keys()) | set(momentum_map.keys()):
            if ticker not in all_tickers:
                market = _detect_market(ticker)
                flow_data = kr_flow_map.get(ticker, {})
                mom_data = momentum_map.get(ticker, {})
                flow_score = None
                volume_score = None
                if flow_data:
                    flow_score = float(flow_data.get("foreign_net", 0)) + float(flow_data.get("inst_net", 0))
                if mom_data:
                    volume_score = float(mom_data.get("change_pct", 0)) + float(mom_data.get("volume_ratio", 0))

                final_details[ticker] = StockDetail(
                    ticker=ticker, market=market, mention_count=0,
                    flow_score=flow_score, volume_score=volume_score,
                    source="market_data", summaries=[],
                )
                market_only_tickers.append(ticker)

        if market_only_tickers:
            themes.append(Theme(
                name="기타 수급 특징주",
                narrative="텔레그램 미언급이나 수급/거래량 이상 감지",
                sentiment="neutral",
                mention_count=0,
                stocks=market_only_tickers,
            ))

        # Step 4: 테마 Top N 선별
        themes.sort(key=lambda t: t.mention_count, reverse=True)
        themes = themes[: self.top_n]

        return ShuffleResult(themes=themes, stock_details=final_details)
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_shuffle_filter.py -v`
예상: 4개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/pipelines/report_stages/shuffle_filter.py tests/pipelines/report_stages/test_shuffle_filter.py
git commit -m "feat: add Stage 3 ShuffleStage with theme merge and market data enrichment"
```

---

### Task 8: Stage 4 — LLM Catalyst

**파일:**
- 생성: `src/pipelines/report_stages/catalyst.py`
- 테스트: `tests/pipelines/report_stages/test_catalyst.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/pipelines/report_stages/test_catalyst.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.pipelines.report_stages.catalyst import CatalystStage
from src.llm.daily_report_models import (
    ShuffleResult, Theme, StockDetail, StockCatalyst,
)


@pytest.fixture
def sample_shuffle_result():
    themes = [
        Theme(name="CPO/광통신", narrative="CPO 수요 증가", sentiment="bull",
              mention_count=5, stocks=["NVDA", "LITE", "A058400"]),
        Theme(name="AI 반도체", narrative="AI 칩 수요", sentiment="bull",
              mention_count=3, stocks=["NVDA", "000660"]),
    ]
    stock_details = {
        "NVDA": StockDetail(ticker="NVDA", market="US", mention_count=5,
                            flow_score=None, volume_score=3.2, source="both",
                            summaries=["NVDA 실적 호조", "AI 칩 수요 폭발"]),
        "LITE": StockDetail(ticker="LITE", market="US", mention_count=3,
                            flow_score=None, volume_score=2.1, source="telegram",
                            summaries=["광트랜시버 수주"]),
        "A058400": StockDetail(ticker="A058400", market="KR", mention_count=2,
                               flow_score=350.0, volume_score=None, source="both",
                               summaries=["코위버 CPO 모듈"]),
        "000660": StockDetail(ticker="000660", market="KR", mention_count=2,
                              flow_score=500.0, volume_score=None, source="telegram",
                              summaries=["HBM 수요"]),
    }
    return ShuffleResult(themes=themes, stock_details=stock_details)


@pytest.fixture
def mock_catalyst_llm():
    """tool-calling 에이전트가 StockCatalyst 리스트를 반환하는 것을 시뮬레이션하는 mock."""
    llm = AsyncMock()
    llm.return_value = [
        StockCatalyst(
            ticker="NVDA", themes=["CPO/광통신", "AI 반도체"],
            news=["NVDA new chip announced"], catalyst_summary="차세대 칩 발표",
        ),
        StockCatalyst(
            ticker="LITE", themes=["CPO/광통신"],
            news=["Lumentum Q2 guidance up"], catalyst_summary="가이던스 상향",
        ),
    ]
    return llm


@pytest.mark.asyncio
async def test_catalyst_stage_returns_catalysts(sample_shuffle_result, mock_catalyst_llm):
    stage = CatalystStage(
        llm=mock_catalyst_llm,
        news_tool=AsyncMock(),
        ticker_resolver=AsyncMock(),
        stocks_per_theme=2,
    )
    # _run_agent를 mock으로 오버라이드
    stage._run_agent = mock_catalyst_llm

    catalysts = await stage.run(sample_shuffle_result)
    assert len(catalysts) >= 1
    assert all(isinstance(c, StockCatalyst) for c in catalysts)


@pytest.mark.asyncio
async def test_catalyst_stage_limits_stocks_per_theme(sample_shuffle_result):
    called_tickers: list[str] = []

    async def mock_agent(themes_json: str, stock_details: dict) -> list[StockCatalyst]:
        import json
        data = json.loads(themes_json)
        for theme in data:
            for stock in theme["stocks"]:
                called_tickers.append(stock["ticker"])
        return []

    stage = CatalystStage(
        llm=AsyncMock(),
        news_tool=AsyncMock(),
        ticker_resolver=AsyncMock(),
        stocks_per_theme=2,
    )
    stage._run_agent = mock_agent
    await stage.run(sample_shuffle_result)

    # CPO에 3개 종목이 있지만 제한이 2 → 상위 2개만 전달되어야 함
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_catalyst.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# src/pipelines/report_stages/catalyst.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool

from src.llm.daily_report_models import ShuffleResult, StockCatalyst
from src.llm.prompts.daily_report import DailyReportPrompts

logger = logging.getLogger(__name__)


@dataclass
class CatalystStage:
    llm: BaseChatModel
    news_tool: object  # NewsTool
    ticker_resolver: object  # TickerResolver
    stocks_per_theme: int = 3

    async def run(self, shuffle_result: ShuffleResult) -> list[StockCatalyst]:
        # 입력 준비: 테마별 상위 N개 종목 + 요약
        themes_for_prompt = []
        for theme in shuffle_result.themes:
            top_stocks = theme.stocks[: self.stocks_per_theme]
            stock_infos = []
            for ticker in top_stocks:
                detail = shuffle_result.stock_details.get(ticker)
                stock_infos.append({
                    "ticker": ticker,
                    "summaries": detail.summaries if detail else [],
                    "flow_score": detail.flow_score if detail else None,
                    "volume_score": detail.volume_score if detail else None,
                })
            themes_for_prompt.append({
                "name": theme.name,
                "narrative": theme.narrative,
                "stocks": stock_infos,
            })

        themes_json = json.dumps(themes_for_prompt, ensure_ascii=False, indent=2)
        return await self._run_agent(themes_json, shuffle_result.stock_details)

    async def _run_agent(self, themes_json: str, stock_details: dict) -> list[StockCatalyst]:
        # NewsTool과 TickerResolver를 langchain tool로 래핑
        news_tool_ref = self.news_tool
        ticker_resolver_ref = self.ticker_resolver

        @tool
        async def search_news(query: str) -> str:
            """주식 티커 또는 키워드로 최근 뉴스를 검색합니다."""
            result = await news_tool_ref.execute(ticker=query, limit=5)
            if not result.success or not result.data:
                return f"{query}에 대한 뉴스가 없습니다"
            return "\n".join(
                f"- {a.title}: {a.summary}" for a in result.data[:5]
            )

        @tool
        async def resolve_ticker(name: str) -> str:
            """회사명을 주식 티커 심볼로 변환합니다."""
            result = await ticker_resolver_ref.resolve(name)
            return f"{name} → {result.resolved_ticker}"

        prompt = DailyReportPrompts.catalyst(themes_json)

        llm_with_tools = self.llm.bind_tools([search_news, resolve_ticker])
        structured = llm_with_tools.with_structured_output(list[StockCatalyst])

        result = await structured.ainvoke(
            prompt,
            config={
                "run_name": "catalyst_analysis",
                "metadata": {"stage": "catalyst"},
            },
        )
        return result
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_catalyst.py -v`
예상: 2개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/pipelines/report_stages/catalyst.py tests/pipelines/report_stages/test_catalyst.py
git commit -m "feat: add Stage 4 CatalystStage with LLM tool calling"
```

---

### Task 9: Stage 5 — LLM Synthesize

**파일:**
- 생성: `src/pipelines/report_stages/synthesize.py`
- 테스트: `tests/pipelines/report_stages/test_synthesize.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/pipelines/report_stages/test_synthesize.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.pipelines.report_stages.synthesize import SynthesizeStage
from src.llm.daily_report_models import (
    IngestResult, ShuffleResult, Theme, StockDetail,
    StockCatalyst, DailyReport,
)


@pytest.fixture
def sample_ingest():
    return IngestResult(
        telegram_messages=[],
        macro_snapshot={"vix": 18.2, "fear_greed": 62, "dxy": 104.2},
        market_news=[{"title": "SPY up", "summary": "Market rises", "source": "SPY", "url": ""}],
        kr_flow=[],
        momentum=[],
    )


@pytest.fixture
def sample_shuffle():
    return ShuffleResult(
        themes=[Theme(name="AI", narrative="AI boom", sentiment="bull",
                      mention_count=10, stocks=["NVDA"])],
        stock_details={"NVDA": StockDetail(
            ticker="NVDA", market="US", mention_count=5,
            flow_score=None, volume_score=3.2, source="telegram",
            summaries=["NVDA 실적 호조"],
        )},
    )


@pytest.fixture
def sample_catalysts():
    return [
        StockCatalyst(ticker="NVDA", themes=["AI"],
                      news=["New chip"], catalyst_summary="차세대 칩"),
    ]


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=DailyReport(
        date="2026-04-13",
        market_pulse="VIX 18.2 | 리스크온",
        narrative_and_themes="AI 인프라 투자 확대",
        featured_analysis="NVDA: 차세대 칩 발표",
    ))
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.asyncio
async def test_synthesize_returns_daily_report(
    sample_ingest, sample_shuffle, sample_catalysts, mock_llm,
):
    stage = SynthesizeStage(llm=mock_llm)
    report = await stage.run(sample_ingest, sample_shuffle, sample_catalysts)

    assert isinstance(report, DailyReport)
    assert report.date == "2026-04-13"
    assert "VIX" in report.market_pulse
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_synthesize.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# src/pipelines/report_stages/synthesize.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from src.llm.daily_report_models import (
    DailyReport,
    IngestResult,
    ShuffleResult,
    StockCatalyst,
)
from src.llm.daily_report_analyzer import synthesize_report

logger = logging.getLogger(__name__)


@dataclass
class SynthesizeStage:
    llm: BaseChatModel

    async def run(
        self,
        ingest: IngestResult,
        shuffle: ShuffleResult,
        catalysts: list[StockCatalyst],
    ) -> DailyReport:
        macro_str = json.dumps(ingest.macro_snapshot, ensure_ascii=False, indent=2)

        news_lines = []
        for n in ingest.market_news:
            news_lines.append(f"- [{n.get('source', '')}] {n.get('title', '')}: {n.get('summary', '')}")
        news_str = "\n".join(news_lines)

        themes_data = []
        for theme in shuffle.themes:
            stock_infos = []
            for ticker in theme.stocks:
                detail = shuffle.stock_details.get(ticker)
                if detail:
                    stock_infos.append({
                        "ticker": ticker,
                        "market": detail.market,
                        "flow_score": detail.flow_score,
                        "volume_score": detail.volume_score,
                    })
            themes_data.append({
                "name": theme.name,
                "narrative": theme.narrative,
                "sentiment": theme.sentiment,
                "mention_count": theme.mention_count,
                "stocks": stock_infos,
            })
        themes_str = json.dumps(themes_data, ensure_ascii=False, indent=2)

        catalysts_data = [c.model_dump() for c in catalysts]
        catalysts_str = json.dumps(catalysts_data, ensure_ascii=False, indent=2)

        return await synthesize_report(
            llm=self.llm,
            macro=macro_str,
            news=news_str,
            themes=themes_str,
            catalysts=catalysts_str,
            metadata={"stage": "synthesize", "theme_count": len(shuffle.themes)},
        )
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/pipelines/report_stages/test_synthesize.py -v`
예상: 1개 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/pipelines/report_stages/synthesize.py tests/pipelines/report_stages/test_synthesize.py
git commit -m "feat: add Stage 5 SynthesizeStage with narrative report generation"
```

---

### Task 10: 파이프라인 오케스트레이터

**파일:**
- 생성: `src/pipelines/daily_report_v2.py`
- 테스트: `tests/pipelines/test_daily_report_v2.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/pipelines/test_daily_report_v2.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from src.pipelines.daily_report_v2 import DailyReportV2Pipeline, STAGE_NAMES


def test_stage_names_order():
    assert STAGE_NAMES == ["ingest", "map", "shuffle", "catalyst", "synthesize"]


def test_stages_from_returns_correct_slice():
    pipeline = DailyReportV2Pipeline.__new__(DailyReportV2Pipeline)
    stages = pipeline._stages_from("shuffle")
    assert stages == ["shuffle", "catalyst", "synthesize"]


def test_stages_from_invalid_raises():
    pipeline = DailyReportV2Pipeline.__new__(DailyReportV2Pipeline)
    with pytest.raises(ValueError, match="Unknown stage"):
        pipeline._stages_from("invalid")


@pytest.mark.asyncio
async def test_run_single_stage_saves_cache(tmp_path):
    mock_ingest = AsyncMock()
    mock_ingest.run.return_value = MagicMock(
        model_dump=MagicMock(return_value={
            "telegram_messages": [], "macro_snapshot": {},
            "market_news": [], "kr_flow": [], "momentum": [],
        }),
    )

    pipeline = DailyReportV2Pipeline(
        ingest_stage=mock_ingest,
        map_stage=AsyncMock(),
        shuffle_stage=AsyncMock(),
        catalyst_stage=AsyncMock(),
        synthesize_stage=AsyncMock(),
        cache_base=tmp_path / ".cache" / "report",
    )

    await pipeline.run(stage="ingest")
    cache_files = list((tmp_path / ".cache" / "report").rglob("*.json"))
    assert any("1_ingest" in f.name for f in cache_files)
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `uv run pytest tests/pipelines/test_daily_report_v2.py -v`
예상: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: 최소 구현 작성**

```python
# src/pipelines/daily_report_v2.py
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass

from src.llm.daily_report_models import (
    DailyReport,
    IngestResult,
    ShuffleResult,
    StockCatalyst,
    IssueExtract,
)
from src.pipelines.report_stages import StageCache
from src.pipelines.report_stages.ingest import IngestStage
from src.pipelines.report_stages.map_issues import MapStage
from src.pipelines.report_stages.shuffle_filter import ShuffleStage
from src.pipelines.report_stages.catalyst import CatalystStage
from src.pipelines.report_stages.synthesize import SynthesizeStage

logger = logging.getLogger(__name__)

STAGE_NAMES = ["ingest", "map", "shuffle", "catalyst", "synthesize"]

STAGE_CACHE_KEYS = {
    "ingest": "1_ingest",
    "map": "2_map",
    "shuffle": "3_shuffle",
    "catalyst": "4_catalyst",
    "synthesize": "5_synthesize",
}


@dataclass
class DailyReportV2Pipeline:
    ingest_stage: IngestStage
    map_stage: MapStage
    shuffle_stage: ShuffleStage
    catalyst_stage: CatalystStage
    synthesize_stage: SynthesizeStage
    cache_base: Path = Path(".cache/report")

    async def run(
        self,
        stage: str | None = None,
        from_stage: str | None = None,
    ) -> DailyReport | None:
        today = datetime.now().strftime("%Y-%m-%d")
        cache = StageCache(StageCache.cache_dir_for_date(self.cache_base, today))

        if stage:
            return await self._run_single_stage(stage, cache)

        stages_to_run = self._stages_from(from_stage) if from_stage else STAGE_NAMES
        return await self._run_stages(stages_to_run, cache)

    async def _run_stages(
        self, stages: list[str], cache: StageCache
    ) -> DailyReport | None:
        ingest_result = None
        map_result = None
        shuffle_result = None
        catalyst_result = None
        report = None

        for stage_name in stages:
            if stage_name == "ingest":
                ingest_result = await self.ingest_stage.run()
                cache.save(STAGE_CACHE_KEYS["ingest"], ingest_result.model_dump())

            elif stage_name == "map":
                if ingest_result is None:
                    ingest_result = IngestResult(**cache.load(STAGE_CACHE_KEYS["ingest"]))
                map_result = await self.map_stage.run(ingest_result.telegram_messages)
                cache.save(STAGE_CACHE_KEYS["map"], [i.model_dump() for i in map_result])

            elif stage_name == "shuffle":
                if ingest_result is None:
                    ingest_result = IngestResult(**cache.load(STAGE_CACHE_KEYS["ingest"]))
                if map_result is None:
                    map_result = [IssueExtract(**i) for i in cache.load(STAGE_CACHE_KEYS["map"])]
                shuffle_result = await self.shuffle_stage.run(
                    map_result, ingest_result.kr_flow, ingest_result.momentum,
                )
                cache.save(STAGE_CACHE_KEYS["shuffle"], shuffle_result.model_dump())

            elif stage_name == "catalyst":
                if shuffle_result is None:
                    shuffle_result = ShuffleResult(**cache.load(STAGE_CACHE_KEYS["shuffle"]))
                catalyst_result = await self.catalyst_stage.run(shuffle_result)
                cache.save(STAGE_CACHE_KEYS["catalyst"], [c.model_dump() for c in catalyst_result])

            elif stage_name == "synthesize":
                if ingest_result is None:
                    ingest_result = IngestResult(**cache.load(STAGE_CACHE_KEYS["ingest"]))
                if shuffle_result is None:
                    shuffle_result = ShuffleResult(**cache.load(STAGE_CACHE_KEYS["shuffle"]))
                if catalyst_result is None:
                    catalyst_result = [StockCatalyst(**c) for c in cache.load(STAGE_CACHE_KEYS["catalyst"])]
                report = await self.synthesize_stage.run(
                    ingest_result, shuffle_result, catalyst_result,
                )
                cache.save(STAGE_CACHE_KEYS["synthesize"], report.model_dump())

        return report

    async def _run_single_stage(self, stage: str, cache: StageCache) -> DailyReport | None:
        return await self._run_stages([stage], cache)

    def _stages_from(self, start: str) -> list[str]:
        if start not in STAGE_NAMES:
            raise ValueError(f"Unknown stage: {start}. 사용 가능: {STAGE_NAMES}")
        idx = STAGE_NAMES.index(start)
        return STAGE_NAMES[idx:]
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `uv run pytest tests/pipelines/test_daily_report_v2.py -v`
예상: 4개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/pipelines/daily_report_v2.py tests/pipelines/test_daily_report_v2.py
git commit -m "feat: add DailyReportV2Pipeline orchestrator with stage caching"
```

---

### Task 11: CLI 통합

**파일:**
- 수정: `src/cli/main.py`

- [ ] **Step 1: 현재 report 커맨드 확인**

실행: `uv run pytest tests/pipelines/test_daily_report_v2.py -v` (Task 10 통과 확인)

- [ ] **Step 2: 파이프라인 팩토리 함수 추가**

`src/cli/main.py`의 기존 `run_daily_report` 함수 아래에 추가:

```python
def create_daily_report_pipeline(provider: str) -> "DailyReportV2Pipeline":
    """일일 리포트 파이프라인의 의존성을 조립하여 반환한다.
    
    테스트 및 스크립트에서 재사용 가능하도록 팩토리 패턴으로 분리.
    """
    import logging
    import os
    from pathlib import Path
    from src.tools.macro import MacroTool
    from src.tools.news import NewsTool
    from src.providers.kis import KISProvider
    from src.providers.ticker_resolver import TickerResolver
    from src.llm.provider import LLMProvider
    from src.pipelines.daily_report_v2 import DailyReportV2Pipeline
    from src.pipelines.report_stages.ingest import IngestStage
    from src.pipelines.report_stages.map_issues import MapStage
    from src.pipelines.report_stages.shuffle_filter import ShuffleStage
    from src.pipelines.report_stages.catalyst import CatalystStage
    from src.pipelines.report_stages.synthesize import SynthesizeStage
    from src.pipelines.report_stages.theme_config import ThemeConfig

    logger = logging.getLogger(__name__)

    # LLM API 키 사전 검증
    api_key_env = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise ValueError(f"Missing {api_key_env} environment variable")

    # LLM 프로바이더 (스테이지별 모델)
    map_llm = LLMProvider.create(provider="openai", model="gpt-4o-mini")
    catalyst_llm = LLMProvider.create(provider="openai", model="gpt-4o")
    synthesize_llm = LLMProvider.create(provider=provider)

    # 도구 및 프로바이더
    macro_tool = MacroTool()
    news_tool = NewsTool()
    ticker_resolver = TickerResolver()
    theme_config = ThemeConfig(Path("themes.yaml"))

    # KIS API 검증
    kis_key = os.getenv("KIS_APP_KEY")
    kis_secret = os.getenv("KIS_APP_SECRET")
    if not (kis_key and kis_secret):
        logger.warning(
            "KIS credentials 설정되지 않았습니다. "
            "한국주식 수급 데이터 및 모멘텀 랭킹이 제외됩니다."
        )
        kis_provider = None
    else:
        kis_provider = KISProvider(app_key=kis_key, app_secret=kis_secret)

    # Telegram 스텁 경고
    class StubTelegramLoader:
        def load(self):
            return []

    telegram_loader = StubTelegramLoader()
    logger.warning(
        "Telegram 로더가 스텁 모드입니다. "
        "telegram-collection 구현 완료 후 실제 데이터를 사용하려면 코드를 업데이트하세요."
    )

    # 스테이지 조립
    ingest_stage = IngestStage(
        macro_tool=macro_tool,
        news_tool=news_tool,
        kis_provider=kis_provider,
        telegram_loader=telegram_loader,
    )
    map_stage = MapStage(
        llm=map_llm,
        known_themes=theme_config.as_prompt_string(),
    )
    shuffle_stage = ShuffleStage(
        ticker_resolver=ticker_resolver,
        merge_llm=map_llm,
        known_themes=theme_config.load(),
    )
    catalyst_stage = CatalystStage(
        llm=catalyst_llm,
        news_tool=news_tool,
        ticker_resolver=ticker_resolver,
    )
    synthesize_stage = SynthesizeStage(llm=synthesize_llm)

    return DailyReportV2Pipeline(
        ingest_stage=ingest_stage,
        map_stage=map_stage,
        shuffle_stage=shuffle_stage,
        catalyst_stage=catalyst_stage,
        synthesize_stage=synthesize_stage,
    )


async def run_daily_report_v2(
    provider: str = "openai",
    stage: str | None = None,
    from_stage: str | None = None,
    no_save: bool = False,
) -> dict:
    """V2 일일 리포트 파이프라인을 실행한다."""
    from datetime import datetime
    from pathlib import Path

    # 캐시 디렉토리 사전 생성 (Stage별 캐시 저장/로드 에러 방지)
    date_str = datetime.now().strftime("%Y-%m-%d")
    cache_dir = Path(".cache/report") / date_str
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 파이프라인 생성 및 실행
    pipeline = create_daily_report_pipeline(provider)
    report = await pipeline.run(stage=stage, from_stage=from_stage)

    result = {"report": report, "no_save": no_save}

    # 최종 리포트 저장 (전체 파이프라인 완료 시에만)
    if report and not no_save and not stage:
        month_str = datetime.now().strftime("%Y-%m")
        report_dir = Path("reports") / month_str
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{date_str}.md"
        md_content = format_daily_report_v2(report)
        report_path.write_text(md_content, encoding="utf-8")
        result["saved_to"] = str(report_path)

    return result
```

- [ ] **Step 3: V2 리포트 포매터 함수 추가**

```python
def format_daily_report_v2(report) -> str:
    """DailyReport를 마크다운 문자열로 포맷팅한다."""
    from src.llm.daily_report_models import DailyReport

    if not isinstance(report, DailyReport):
        return "리포트 생성에 실패했습니다."

    lines = [
        f"# Daily Market Report — {report.date}",
        "",
        "## 시장 온도",
        "",
        report.market_pulse,
        "",
        "## 시장 내러티브 & 주목 테마",
        "",
        report.narrative_and_themes,
        "",
        "## 주도주 분석",
        "",
        report.featured_analysis,
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: report 커맨드 교체**

`src/cli/main.py`의 기존 `report` 커맨드를 교체:

```python
@app.command()
def report(
    provider: str = typer.Option("openai", "--provider", "-p", help="LLM 프로바이더 (openai|anthropic)"),
    stage: str = typer.Option(None, "--stage", help="단일 스테이지 실행 (ingest|map|shuffle|catalyst|synthesize)"),
    from_stage: str = typer.Option(None, "--from", help="해당 스테이지부터 끝까지 실행"),
    no_save: bool = typer.Option(False, "--no-save", help="리포트 파일 저장 생략"),
):
    """일일 시장 리포트 (V2: 테마 중심 내러티브)"""
    import asyncio

    console.print("\n[bold]Daily Market Report V2[/bold]\n")

    result = asyncio.run(run_daily_report_v2(
        provider=provider,
        stage=stage,
        from_stage=from_stage,
        no_save=no_save,
    ))

    report_obj = result.get("report")
    if report_obj:
        md = format_daily_report_v2(report_obj)
        console.print(Markdown(md))
        if "saved_to" in result:
            console.print(f"\n[dim]저장 위치: {result['saved_to']}[/dim]")
    elif stage:
        console.print(f"[green]스테이지 '{stage}' 완료. .cache/report/ 에서 결과를 확인하세요.[/green]")
    else:
        console.print("[red]리포트 생성에 실패했습니다.[/red]")
```

- [ ] **Step 5: CLI 스모크 테스트**

실행: `uv run jarvis report --help`
예상: `--stage`, `--from`, `--no-save` 옵션이 표시됨

- [ ] **Step 6: 커밋**

```bash
git add src/cli/main.py
git commit -m "feat: replace report command with V2 pipeline (stage-based, theme-centric)"
```

---

### Task 12: 문서 업데이트

**파일:**
- 수정: `README.md` — report 커맨드 설명 업데이트
- 수정: `docs/CLI_USAGE.md` — report 섹션에 새 옵션 추가
- 수정: `CLAUDE.md` — Commands 섹션 업데이트

- [ ] **Step 1: README.md report 섹션 업데이트**

```markdown
uv run jarvis report            # 일일 시장 리포트 (V2: 테마 중심 내러티브)
```

- [ ] **Step 2: docs/CLI_USAGE.md report 섹션 교체**

기존 report 섹션을 다음으로 교체:

```markdown
### 3. report - 일일 시장 리포트 (V2)

**특징:**
- 텔레그램 + 뉴스 + 매크로 + 수급 데이터 병렬 수집
- LLM Map-Reduce로 시장 테마/내러티브 추출
- 주도주 촉매 뉴스 자동 매칭
- Stage별 독립 실행으로 프롬프트 튜닝 가능

**요구사항:**
- `OPENAI_API_KEY` 필요 (Map, Catalyst 단계)
- `ANTHROPIC_API_KEY` 선택 (Synthesize 단계)
- `KIS_APP_KEY`, `KIS_APP_SECRET` 선택 (수급 데이터)

**사용법:**
\`\`\`bash
# 전체 파이프라인 실행
uv run jarvis report
uv run jarvis report --provider anthropic

# Stage별 독립 실행 (튜닝용)
uv run jarvis report --stage ingest
uv run jarvis report --stage map
uv run jarvis report --stage shuffle
uv run jarvis report --stage catalyst
uv run jarvis report --stage synthesize

# 특정 Stage부터 이어서 실행
uv run jarvis report --from shuffle

# 파일 저장 안함
uv run jarvis report --no-save
\`\`\`

**출력 내용:**
- **시장 온도:** 매크로 수치 해석 + 시장 분위기 (10줄 이내)
- **시장 내러티브 & 주목 테마:** 테마 간 연결고리, 부상 이유
- **주도주 분석:** 테마별 핵심 종목 + 촉매 뉴스 + 수급 근거

**리포트 저장:** `reports/YYYY-MM/YYYY-MM-DD.md`
```

- [ ] **Step 3: CLAUDE.md Commands 섹션 업데이트**

```markdown
uv run jarvis report            # 일일 시장 리포트 (V2: 테마 중심)
```

- [ ] **Step 4: 커밋**

```bash
git add README.md docs/CLI_USAGE.md CLAUDE.md
git commit -m "docs: update report command documentation for V2 pipeline"
```

---

### Task 13: .gitignore 항목 추가

**파일:**
- 수정: `.gitignore`

- [ ] **Step 1: 캐시 및 리포트 디렉토리를 .gitignore에 추가**

`.gitignore`에 추가:

```
# Daily Report V2 캐시
.cache/report/

# 생성된 리포트
reports/
```

- [ ] **Step 2: 커밋**

```bash
git add .gitignore
git commit -m "chore: add .cache/report and reports/ to .gitignore"
```
