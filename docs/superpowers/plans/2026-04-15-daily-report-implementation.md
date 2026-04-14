# Daily Report Pipeline 구현 계획

> **에이전트 워커용:** 이 계획을 단계별로 실행하려면 superpowers:subagent-driven-development (권장) 또는 superpowers:executing-plans 스킬을 사용하세요. 체크박스 (`- [ ]`) 문법으로 진행 상황을 추적합니다.

**목표:** 텔레그램 메시지를 한글 일일 시장 리포트로 변환하는 4단계 LLM 파이프라인 구축

**아키텍처:** Map-Reduce 패턴 + Shuffle 정규화 레이어. Map/Shuffle은 gpt-4o (일관성), Reduce/Wrapup은 gpt-5.2 (분석 깊이). 각 단계는 독립적으로 테스트 가능하며 프롬프트 버전 관리 지원.

**기술 스택:** Python 3.12, langchain, duckduckgo-search, pydantic, pytest

---

## 핵심: LLM 프롬프트 튜닝 전략

**핵심 철학**: 프롬프트는 코드다. 버전 관리하고, 테스트하고, 데이터 기반으로 반복 개선한다.

### 프롬프트 개발 워크플로우

```
1. 초기 프롬프트 작성 (prompts.py에)
2. 프롬프트 테스트 픽스처 생성 (실제 텔레그램 데이터)
3. Stage 독립 실행 (python -m src.pipelines.daily_report.stages.<stage>_stage)
4. 출력 품질 평가 (수동 + 메트릭)
5. 실패 패턴 기반 프롬프트 개선
6. 프롬프트 버전 관리 (평가 결과와 함께 git commit)
7. 품질 기준 충족까지 반복
```

### 품질 평가 프레임워크

**Map Stage 메트릭:**
- 클러스터링 비율: 이슈당 평균 메시지 수 (목표: 5-10)
- 테마 다양성: 청크당 고유 테마 수 (목표: 3-7)
- 키워드 정확도: 실제 종목/기술용어인 키워드 비율 (목표: >80%)

**Shuffle Stage 메트릭:**
- 정규화 비율: 원본 테마 / 정규화 테마 (목표: 0.3-0.7)
- 의미 정확도: 테마 그룹핑 수동 검토 (목표: >90% 적절)

**Reduce Stage 메트릭:**
- 한글 유창성: 수동 검토 (목표: 원어민 수준)
- 이모지 적절성: 적절한 이모지를 가진 NewsItem 비율 (목표: 100%)
- Impact 문구 존재: Impact 있는 비율 (목표: 100%)
- Bullet 형식: 적절한 구조의 비율 (목표: 100%)

**Wrapup Stage 메트릭:**
- 크로스 테마 연결: 2개 이상 테마를 연결하는 인사이트 비율 (목표: >80%)
- 인사이트 독창성: NewsItem 단순 요약이 아닌지 (수동 검토)

### 프롬프트 버전 관리 방식

```python
# src/pipelines/daily_report/prompts.py 구조
MAP_PROMPT_V1 = """..."""
MAP_PROMPT_V2 = """..."""  # Few-shot 예시 추가
MAP_PROMPT = MAP_PROMPT_V2  # 현재 활성 버전

# Git 커밋 메시지에 평가 결과 포함
# "prompt: Map 클러스터링 개선 (v1→v2)
#
# 변경사항: Bloom Energy few-shot 예시 추가
# 결과: 클러스터링 비율 3.2 → 7.8, 테마 다양성 유지"
```

### Few-Shot 예시 관리

**저장 위치**: `src/pipelines/daily_report/examples/`
- `map_examples.py`: 클러스터링 예시 (Bloom Energy 케이스)
- `shuffle_examples.py`: 테마 정규화 예시
- `reduce_examples.py`: 한글 스타일 예시 (이모지, Impact)

**좋은 예시의 기준**:
- 2026-04-14 텔레그램 메시지 실제 데이터 사용
- 엣지 케이스 커버 (다중 섹터 기업, 모호한 테마)
- 원하는 출력 형식을 명시적으로 보여줌

### Stage별 독립 테스트 설정

각 단계는 독립 실행을 위한 CLI 진입점 제공:

```bash
# 특정 날짜로 Map stage 테스트
python -m src.pipelines.daily_report.stages.map_stage --date 2026-04-14 --output map_output.json

# Map 출력으로 Shuffle stage 테스트
python -m src.pipelines.daily_report.stages.shuffle_stage --input map_output.json --output shuffle_output.json

# 특정 테마로 Reduce stage 테스트
python -m src.pipelines.daily_report.stages.reduce_stage --input shuffle_output.json --theme "AI 데이터센터 전력" --output reduce_output.json

# 전체 파이프라인
uv run jarvis report --date 2026-04-14
```

**반복 루프**:
1. Stage 독립 실행
2. 출력을 `tests/fixtures/stage_outputs/`에 저장
3. 출력 품질 검토 (수동 + 메트릭 스크립트)
4. 실패 패턴 식별
5. prompts.py에서 프롬프트 업데이트
6. Stage 재실행
7. 출력 비교 (`diff` 또는 비교 스크립트)
8. 품질 개선 시 커밋

---

## 파일 구조

```
src/pipelines/daily_report/
├── __init__.py              # run_daily_report() export
├── pipeline.py              # 전체 stage 오케스트레이션
├── models.py                # Pydantic 모델
├── prompts.py              # 모든 프롬프트 + 버전 관리
├── examples/               # Few-shot 예시
│   ├── __init__.py
│   ├── map_examples.py
│   ├── shuffle_examples.py
│   └── reduce_examples.py
├── stages/
│   ├── __init__.py
│   ├── ingest_stage.py     # CSV + 매크로 데이터
│   ├── map_stage.py        # 청크 → MappedIssue (gpt-4o)
│   ├── shuffle_stage.py    # 테마 정규화 (gpt-4o)
│   ├── reduce_stage.py     # 테마 → NewsItem (gpt-5.2)
│   └── wrapup_stage.py     # 크로스 테마 인사이트 (gpt-5.2)
└── renderer.py             # 마크다운 생성

tests/pipelines/daily_report/
├── __init__.py
├── conftest.py             # 공유 픽스처
├── fixtures/               # 실제 데이터 스냅샷
│   ├── telegram_messages_2026-04-14.json
│   └── stage_outputs/      # 비교 테스트용
├── test_models.py
├── test_ingest_stage.py
├── test_map_stage.py
├── test_shuffle_stage.py
├── test_reduce_stage.py
├── test_wrapup_stage.py
├── test_pipeline.py        # 통합 테스트
└── evaluate_quality.py     # 메트릭 스크립트

scripts/
└── tune_prompts.py         # 대화형 프롬프트 튜닝 도구

reports/                    # 출력 디렉토리
└── 2026-04/
    └── 2026-04-14_daily_report.md
```

---

## Task 1: 프로젝트 설정 & 모델

**파일:**
- 생성: `src/pipelines/daily_report/__init__.py`
- 생성: `src/pipelines/daily_report/models.py`
- 생성: `tests/pipelines/daily_report/__init__.py`
- 생성: `tests/pipelines/daily_report/conftest.py`

- [ ] **Step 1: 패키지 구조 생성**

```bash
mkdir -p src/pipelines/daily_report/stages
mkdir -p src/pipelines/daily_report/examples
mkdir -p tests/pipelines/daily_report/fixtures/stage_outputs
mkdir -p reports/2026-04
touch src/pipelines/daily_report/__init__.py
touch src/pipelines/daily_report/stages/__init__.py
touch src/pipelines/daily_report/examples/__init__.py
touch tests/pipelines/daily_report/__init__.py
```

- [ ] **Step 2: Pydantic 모델 작성**

`src/pipelines/daily_report/models.py` 생성:

```python
"""Daily report 파이프라인 데이터 모델."""
from datetime import datetime
from typing import Dict, List, Literal
from pydantic import BaseModel, Field


class MacroSnapshot(BaseModel):
    """시장 매크로 지표 스냅샷."""
    date: str
    us_markets: Dict[str, float] = Field(
        description="미국 시장 변동률. Keys: S&P500, NASDAQ, DOW"
    )
    kr_markets: Dict[str, float] = Field(
        description="한국 시장 변동률. Keys: KOSPI, KOSDAQ"
    )
    vix: float
    fear_greed: int = Field(ge=0, le=100)
    krw_usd: float


class TelegramMessage(BaseModel):
    """텔레그램 메시지 하나."""
    channel_id: str
    message_id: str
    timestamp: datetime
    text: str


class IngestResult(BaseModel):
    """Ingest stage 출력."""
    date: str
    macro: MacroSnapshot
    messages: List[TelegramMessage]


class MappedIssue(BaseModel):
    """Map stage에서 추출한 이슈."""
    title: str = Field(description="한글 제목")
    summary: str = Field(description="한글 요약")
    themes: List[str] = Field(
        description="2-3개의 의미론적 테마 (섹터 아님)",
        min_length=1,
        max_length=3
    )
    keywords: List[str] = Field(
        description="뉴스 검색용 종목명, 기술용어"
    )
    sentiment: Literal["bull", "bear", "neutral"]
    source_ids: List[str] = Field(description="원본 메시지 ID")


class ShuffleResult(BaseModel):
    """Shuffle stage 출력 (테마 정규화)."""
    canonical_themes: Dict[str, List[str]] = Field(
        description="정규화명 → 원본 테마명 매핑"
    )
    theme_groups: Dict[str, List[MappedIssue]] = Field(
        description="정규화 테마별로 그룹핑된 이슈"
    )


class StockDetail(BaseModel):
    """관련 종목 정보."""
    name: str
    ticker: str
    catalyst: str = Field(description="한글 촉매 설명")


class NewsItem(BaseModel):
    """Reduce stage의 테마별 분석."""
    theme: str = Field(description="한글 정규화 테마명")
    emoji: str = Field(description="단일 이모지: 🚀📈⚠️ℹ️📉⚡")
    summary: str = Field(description="한글 bullet points")
    impact: str = Field(description="한글 impact 문구")
    stocks: List[StockDetail] = Field(default_factory=list)


class DailyReport(BaseModel):
    """최종 리포트 출력."""
    date: str
    macro: MacroSnapshot
    insights: List[str] = Field(description="한글 크로스 테마 인사이트")
    news_items: List[NewsItem]
```

- [ ] **Step 3: 모델 테스트 작성**

`tests/pipelines/daily_report/test_models.py` 생성:

```python
"""Daily report Pydantic 모델 테스트."""
import pytest
from datetime import datetime
from src.pipelines.daily_report.models import (
    MacroSnapshot,
    TelegramMessage,
    MappedIssue,
    ShuffleResult,
    NewsItem,
    DailyReport,
)


def test_macro_snapshot_validation():
    """MacroSnapshot 필드 검증 테스트."""
    macro = MacroSnapshot(
        date="2026-04-14",
        us_markets={"S&P500": 1.2, "NASDAQ": 1.5, "DOW": 0.8},
        kr_markets={"KOSPI": 2.1, "KOSDAQ": 1.8},
        vix=19.1,
        fear_greed=52,
        krw_usd=1320.0,
    )
    assert macro.fear_greed == 52
    
    # Fear & Greed는 0-100이어야 함
    with pytest.raises(ValueError):
        MacroSnapshot(
            date="2026-04-14",
            us_markets={},
            kr_markets={},
            vix=19.1,
            fear_greed=101,
            krw_usd=1320.0,
        )


def test_mapped_issue_themes_constraint():
    """MappedIssue themes 길이 제약 테스트."""
    # 유효: 1-3개 테마
    issue = MappedIssue(
        title="테스트",
        summary="요약",
        themes=["AI 전력", "데이터센터"],
        keywords=["Bloom Energy"],
        sentiment="bull",
        source_ids=["msg1"],
    )
    assert len(issue.themes) == 2
    
    # 무효: 0개 테마
    with pytest.raises(ValueError):
        MappedIssue(
            title="테스트",
            summary="요약",
            themes=[],
            keywords=[],
            sentiment="bull",
            source_ids=[],
        )
    
    # 무효: >3개 테마
    with pytest.raises(ValueError):
        MappedIssue(
            title="테스트",
            summary="요약",
            themes=["A", "B", "C", "D"],
            keywords=[],
            sentiment="bull",
            source_ids=[],
        )


def test_news_item_emoji_field():
    """NewsItem emoji 필드 테스트."""
    item = NewsItem(
        theme="AI 전력",
        emoji="🚀",
        summary="- 내용",
        impact="Impact: 긍정적",
    )
    assert item.emoji == "🚀"
```

- [ ] **Step 4: pytest 픽스처 작성**

`tests/pipelines/daily_report/conftest.py` 생성:

```python
"""Daily report 파이프라인 공유 테스트 픽스처."""
import pytest
from datetime import datetime
from src.pipelines.daily_report.models import (
    MacroSnapshot,
    TelegramMessage,
    MappedIssue,
)


@pytest.fixture
def sample_macro():
    """샘플 매크로 스냅샷."""
    return MacroSnapshot(
        date="2026-04-14",
        us_markets={"S&P500": 1.2, "NASDAQ": 1.5, "DOW": 0.8},
        kr_markets={"KOSPI": 2.1, "KOSDAQ": 1.8},
        vix=19.1,
        fear_greed=52,
        krw_usd=1320.0,
    )


@pytest.fixture
def sample_messages():
    """샘플 텔레그램 메시지."""
    return [
        TelegramMessage(
            channel_id="test_channel",
            message_id="msg1",
            timestamp=datetime(2026, 4, 14, 9, 0),
            text="Bloom Energy, Oracle에 연료전지 1.2GW 공급",
        ),
        TelegramMessage(
            channel_id="test_channel",
            message_id="msg2",
            timestamp=datetime(2026, 4, 14, 9, 15),
            text="LS ELECTRIC 북미 DC 배전반 1700억 수주",
        ),
        TelegramMessage(
            channel_id="test_channel",
            message_id="msg3",
            timestamp=datetime(2026, 4, 14, 9, 30),
            text="데이터센터 전력 수요 2030년 1350TWh 전망",
        ),
    ]


@pytest.fixture
def sample_mapped_issue():
    """샘플 매핑된 이슈."""
    return MappedIssue(
        title="AI 데이터센터 전력 인프라 투자 급증",
        summary="Oracle-Bloom Energy 계약, LS 수주 등",
        themes=["AI 데이터센터", "전력 인프라"],
        keywords=["Bloom Energy", "Oracle", "LS ELECTRIC"],
        sentiment="bull",
        source_ids=["msg1", "msg2", "msg3"],
    )
```

- [ ] **Step 5: 모델 테스트 실행**

```bash
uv run pytest tests/pipelines/daily_report/test_models.py -v
```

예상 결과: 모든 테스트 통과

- [ ] **Step 6: 모델 및 테스트 커밋**

```bash
git add src/pipelines/daily_report/models.py tests/pipelines/daily_report/
git commit -m "feat(daily_report): Pydantic 모델 추가 및 검증

- MacroSnapshot: 시장 지표
- MappedIssue: 테마 (1-3개 길이 제약)
- ShuffleResult: 테마 정규화 출력
- NewsItem: 이모지 포함 한글 출력
- DailyReport: 최종 리포트 구조

테스트: 모델 검증, 테마 제약, 이모지 필드"
```

---

## Task 2: Ingest Stage (CSV + 매크로 데이터)

**파일:**
- 생성: `src/pipelines/daily_report/stages/ingest_stage.py`
- 생성: `tests/pipelines/daily_report/test_ingest_stage.py`
- 수정: `src/tools/macro.py` (필요 시 누락 함수 추가)

- [ ] **Step 1: Ingest stage 구현 작성**

`src/pipelines/daily_report/stages/ingest_stage.py` 생성:

```python
"""Ingest stage: 텔레그램 메시지 및 매크로 데이터 로드."""
import csv
from pathlib import Path
from datetime import datetime, timedelta
import yfinance as yf
from src.pipelines.daily_report.models import (
    IngestResult,
    MacroSnapshot,
    TelegramMessage,
)
from src.tools.macro import get_vix, get_fear_greed


def ingest(date: str, data_dir: str = "data") -> IngestResult:
    """
    주어진 날짜의 텔레그램 메시지와 매크로 데이터 로드.
    
    Args:
        date: 날짜 문자열 (YYYY-MM-DD)
        data_dir: 루트 데이터 디렉토리
    
    Returns:
        매크로 및 메시지가 포함된 IngestResult
    
    Raises:
        FileNotFoundError: 해당 날짜의 CSV 파일이 없을 때
    """
    macro = _fetch_macro(date)
    messages = _load_telegram_csvs(date, data_dir)
    
    if not messages:
        raise FileNotFoundError(
            f"{date}의 텔레그램 메시지를 찾을 수 없습니다. "
            f"실행: uv run jarvis telegram fetch {date}"
        )
    
    return IngestResult(date=date, macro=macro, messages=messages)


def _fetch_macro(date: str) -> MacroSnapshot:
    """주어진 날짜의 매크로 지표 수집."""
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    prev_date = date_obj - timedelta(days=1)
    
    # 미국 시장 (전날 종가)
    us_tickers = {"S&P500": "^GSPC", "NASDAQ": "^IXIC", "DOW": "^DJI"}
    us_markets = {}
    for name, ticker in us_tickers.items():
        try:
            data = yf.Ticker(ticker).history(period="2d")
            if len(data) >= 2:
                pct_change = (
                    (data["Close"].iloc[-1] - data["Close"].iloc[-2])
                    / data["Close"].iloc[-2]
                    * 100
                )
                us_markets[name] = round(pct_change, 2)
            else:
                us_markets[name] = 0.0
        except Exception:
            us_markets[name] = 0.0
    
    # 한국 시장 (당일 종가)
    kr_tickers = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}
    kr_markets = {}
    for name, ticker in kr_tickers.items():
        try:
            data = yf.Ticker(ticker).history(period="2d")
            if len(data) >= 2:
                pct_change = (
                    (data["Close"].iloc[-1] - data["Close"].iloc[-2])
                    / data["Close"].iloc[-2]
                    * 100
                )
                kr_markets[name] = round(pct_change, 2)
            else:
                kr_markets[name] = 0.0
        except Exception:
            kr_markets[name] = 0.0
    
    # VIX 및 Fear & Greed
    try:
        vix = get_vix()
    except Exception:
        vix = 0.0
    
    try:
        fear_greed = get_fear_greed()
    except Exception:
        fear_greed = 50
    
    # KRW/USD (yfinance KRW=X 사용)
    try:
        krw_data = yf.Ticker("KRW=X").history(period="1d")
        krw_usd = round(krw_data["Close"].iloc[-1], 1) if len(krw_data) > 0 else 1320.0
    except Exception:
        krw_usd = 1320.0
    
    return MacroSnapshot(
        date=date,
        us_markets=us_markets,
        kr_markets=kr_markets,
        vix=vix,
        fear_greed=fear_greed,
        krw_usd=krw_usd,
    )


def _load_telegram_csvs(date: str, data_dir: str) -> List[TelegramMessage]:
    """주어진 날짜의 모든 텔레그램 CSV 로드."""
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    year_month = date_obj.strftime("%Y-%m")
    csv_dir = Path(data_dir) / year_month
    
    if not csv_dir.exists():
        return []
    
    # 날짜 패턴과 일치하는 모든 CSV 찾기
    pattern = f"{date}-*.csv"
    csv_files = list(csv_dir.glob(pattern))
    
    messages = []
    for csv_file in csv_files:
        # 파일명에서 channel_id 추출 (예: "2026-04-14-shinhanresearch.csv")
        channel_id = csv_file.stem.split("-", 3)[-1]
        
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                messages.append(
                    TelegramMessage(
                        channel_id=channel_id,
                        message_id=row["message_id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        text=row["text"],
                    )
                )
    
    return messages


# 테스트용 CLI 진입점
if __name__ == "__main__":
    import sys
    import json
    
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-14"
    result = ingest(date)
    
    print(f"✓ {len(result.messages)}개 메시지 로드")
    print(f"✓ 매크로: VIX={result.macro.vix}, F&G={result.macro.fear_greed}")
    print(f"✓ 미국 시장: {result.macro.us_markets}")
    print(f"✓ 한국 시장: {result.macro.kr_markets}")
    
    # 다음 stage 테스트용으로 저장
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/ingest_{date}.json"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    print(f"✓ {output_file}에 저장")
```

- [ ] **Step 2: Ingest stage 테스트 작성**

`tests/pipelines/daily_report/test_ingest_stage.py` 생성:

```python
"""Ingest stage 테스트."""
import pytest
from unittest.mock import patch, MagicMock
from src.pipelines.daily_report.stages.ingest_stage import ingest, _fetch_macro


def test_ingest_no_csv_raises_error():
    """CSV 파일이 없을 때 ingest가 에러를 발생시키는지 테스트."""
    with pytest.raises(FileNotFoundError, match="텔레그램 메시지를 찾을 수 없습니다"):
        ingest("2099-01-01", data_dir="nonexistent")


@patch("src.pipelines.daily_report.stages.ingest_stage.get_vix")
@patch("src.pipelines.daily_report.stages.ingest_stage.get_fear_greed")
@patch("yfinance.Ticker")
def test_fetch_macro_handles_api_failures(mock_ticker, mock_fg, mock_vix):
    """_fetch_macro가 API 실패 시 기본값을 반환하는지 테스트."""
    # 모든 API 실패 시뮬레이션
    mock_vix.side_effect = Exception("VIX API 다운")
    mock_fg.side_effect = Exception("F&G API 다운")
    mock_ticker.return_value.history.side_effect = Exception("yfinance 다운")
    
    macro = _fetch_macro("2026-04-14")
    
    # 크래시하지 않고 기본값 반환해야 함
    assert macro.vix == 0.0
    assert macro.fear_greed == 50
    assert macro.us_markets["S&P500"] == 0.0
    assert macro.kr_markets["KOSPI"] == 0.0
    assert macro.krw_usd == 1320.0


def test_ingest_with_real_data():
    """실제 2026-04-14 데이터로 통합 테스트."""
    # 실제 CSV 파일 사용
    result = ingest("2026-04-14")
    
    assert result.date == "2026-04-14"
    assert len(result.messages) > 0
    assert result.macro.vix >= 0
    assert 0 <= result.macro.fear_greed <= 100
```

- [ ] **Step 3: Ingest 테스트 실행**

```bash
uv run pytest tests/pipelines/daily_report/test_ingest_stage.py -v
```

예상 결과: 테스트 통과 (통합 테스트는 실제 CSV 사용)

- [ ] **Step 4: Ingest CLI 수동 테스트**

```bash
python -m src.pipelines.daily_report.stages.ingest_stage 2026-04-14
```

예상 결과: 메시지 개수, 매크로 데이터 출력, 픽스처 JSON 저장

- [ ] **Step 5: Ingest stage 커밋**

```bash
git add src/pipelines/daily_report/stages/ingest_stage.py tests/pipelines/daily_report/test_ingest_stage.py
git commit -m "feat(daily_report): CSV 및 매크로 데이터용 Ingest stage 추가

- data/YYYY-MM/ 디렉토리에서 텔레그램 CSV 로드
- 매크로 수집: 미국/한국 시장, VIX, Fear & Greed, KRW/USD
- API 실패 시 graceful degradation (기본값)
- CLI: python -m src.pipelines.daily_report.stages.ingest_stage <date>
- 테스트: 에러 처리, API 실패 복원력, 통합 테스트"
```

---

## Task 3: 프롬프트 인프라 & 예시

**파일:**
- 생성: `src/pipelines/daily_report/prompts.py`
- 생성: `src/pipelines/daily_report/examples/map_examples.py`
- 생성: `src/pipelines/daily_report/examples/shuffle_examples.py`
- 생성: `src/pipelines/daily_report/examples/reduce_examples.py`

- [ ] **Step 1: 버전 관리 구조로 prompts 모듈 생성**

`src/pipelines/daily_report/prompts.py` 생성:

```python
"""
Daily report 파이프라인용 LLM 프롬프트.

버전 관리 규칙:
- STAGE_PROMPT_V1, V2 등으로 과거 버전 보관
- STAGE_PROMPT는 현재 활성 버전을 가리킴
- 버전 변경 시 Git 커밋에 평가 결과 문서화
"""

# ============================================================================
# MAP STAGE PROMPTS
# ============================================================================

MAP_PROMPT_V1 = """당신은 한국 금융 시장 전문 애널리스트입니다.
텔레그램 메시지들을 분석하여 주요 이슈를 추출하세요.

**핵심 지침**:
1. 유사한 주제의 메시지는 하나의 이슈로 통합 (예: Bloom Energy 관련 메시지 4개 → 1개 이슈)
2. 각 이슈에 2-3개의 **테마** 태그 부여 (예: ["AI 전력 인프라", "데이터센터"])
   - 테마는 섹터가 아님: "반도체" (X) → "AI 메모리 업사이클" (O)
   - 테마는 의미론적 주제: "전력 부족", "공급망 리쇼어링", "실적 서프라이즈"
3. 종목명, 기술용어를 keywords에 추출
4. 감성: bull(긍정적 호재), bear(부정적 악재), neutral(중립 정보)
5. 한글로 작성

**Few-shot 예시**:
{examples}

**입력 메시지**:
{messages}

**출력 형식**: JSON array of MappedIssue
```json
[
  {{
    "title": "이슈 제목 (한글)",
    "summary": "이슈 요약 (한글, 2-3 문장)",
    "themes": ["테마1", "테마2"],
    "keywords": ["종목명", "기술용어"],
    "sentiment": "bull|bear|neutral",
    "source_ids": ["msg1", "msg2"]
  }}
]
```
"""

MAP_PROMPT = MAP_PROMPT_V1  # 현재 활성 버전


# ============================================================================
# SHUFFLE STAGE PROMPTS
# ============================================================================

SHUFFLE_PROMPT_V1 = """다음은 여러 청크에서 추출된 테마들입니다.
유사한 의미의 테마들을 하나의 정규화된 이름으로 통합하세요.

**지침**:
1. 의미가 같으면 통합 (예: "AI 전력", "AI DC 파워", "데이터센터 전력" → "AI 데이터센터 전력 인프라")
2. 정규화 이름은 가장 포괄적이고 명확한 한글 표현 사용
3. 너무 광범위하게 묶지 말 것 (예: "AI"로만 통합하면 안됨)
4. 명확히 다른 주제는 분리 유지

**Few-shot 예시**:
{examples}

**입력 테마 리스트**:
{themes}

**출력 형식**: JSON object
```json
{{
  "정규화_테마1": ["원본_테마1", "원본_테마2", "원본_테마3"],
  "정규화_테마2": ["원본_테마4", "원본_테마5"]
}}
```
"""

SHUFFLE_PROMPT = SHUFFLE_PROMPT_V1  # 현재 활성 버전


# ============================================================================
# REDUCE STAGE PROMPTS
# ============================================================================

REDUCE_PROMPT_V1 = """당신은 한국 금융 시장 전문 애널리스트입니다.
특정 테마에 대한 분석 리포트를 작성하세요.

**테마**: {theme}

**관련 이슈들**:
{issues}

**관련 뉴스**:
{news_articles}

**작성 지침**:
1. 한글로 작성
2. 이모지 사용:
   - 🚀 강세/호재
   - 📈 상승 추세
   - ⚠️ 주의/리스크
   - 📉 약세
   - ℹ️ 중립/정보
   - ⚡ 긴급/중요
3. Summary: Bullet point 형식으로 핵심 내용 정리 (이모지 포함)
4. Impact: **(Impact: ...)** 형식으로 시장 영향 평가
5. 관련 종목이 있으면 StockDetail 포함 (종목명, 티커, 촉매 뉴스)

**Few-shot 예시**:
{examples}

**출력 형식**: JSON object
```json
{{
  "theme": "{theme}",
  "emoji": "⚡",
  "summary": "🔋 Oracle-Bloom Energy 2.8GW 연료전지 계약\\n📈 LS ELECTRIC 북미 배전반 1,700억원 수주\\n⚡ 2030년 DC 전력 수요 1,350TWh 전망 (+220%)",
  "impact": "전력 인프라 병목 해소로 AI 투자 가속화. 한국 전력기기 3사 수주 레벨업 기대",
  "stocks": [
    {{
      "name": "LS ELECTRIC",
      "ticker": "010120.KS",
      "catalyst": "북미 AI DC 배전반 1,700억원 공급 계약"
    }}
  ]
}}
```
"""

REDUCE_PROMPT = REDUCE_PROMPT_V1  # 현재 활성 버전


# ============================================================================
# WRAPUP STAGE PROMPTS
# ============================================================================

WRAPUP_PROMPT_V1 = """당신은 시장 전략가입니다.
여러 테마들을 종합하여 오늘의 핵심 시장 내러티브를 도출하세요.

**테마별 분석**:
{news_items}

**작성 지침**:
1. 한글로 작성
2. 여러 테마를 연결하는 메타 인사이트 3-5개 도출
3. 각 인사이트는 2-3줄로 간결하게
4. 이모지 활용 (🔥💡🌊⚠️ 등)
5. 단순 요약 금지 - 테마 간 연결과 시사점 도출

**출력 형식**: JSON array of strings
```json
[
  "🔥 AI 슈퍼사이클: 데이터센터 전력 인프라 + 반도체 메모리 업사이클 + 전력기기 수주 급증 → 통합 투자 테마 형성",
  "💡 공급망 리쇼어링: 미국 CHIPS Act + 한국 전력기기 수출 + 일본 소재 확대 → 비중국 밸류체인 재편 가속"
]
```
"""

WRAPUP_PROMPT = WRAPUP_PROMPT_V1  # 현재 활성 버전
```

- [ ] **Step 2: Map 예시 생성**

`src/pipelines/daily_report/examples/map_examples.py` 생성:

```python
"""Map stage용 Few-shot 예시."""

# 실제 2026-04-14 텔레그램 데이터 기반
MAP_EXAMPLE_1 = """
**입력 메시지**:
```
[msg1] Bloom Energy, Oracle에 연료전지 1.2GW 공급 계약
[msg2] LS ELECTRIC 북미 AI 데이터센터 배전반 1,700억원 수주
[msg3] Bloom Energy 워런트 발행으로 Oracle AI 인프라 확장 자금 조달
[msg4] 데이터센터 전력 수요 2030년 1,350TWh 전망 (+220%)
[msg5] 현대차 1분기 영업이익 3.2조 예상, 컨센서스 하회
[msg6] 기아 미국 판매 부진, SUV 재고 증가
```

**출력**:
```json
[
  {
    "title": "AI 데이터센터 전력 인프라 투자 급증",
    "summary": "Oracle-Bloom Energy 2.8GW 규모 연료전지 공급 계약 체결. LS ELECTRIC 북미 배전반 1,700억원 수주. 2030년까지 데이터센터 전력 수요 220% 증가 전망으로 인프라 투자 가속화",
    "themes": ["AI 데이터센터", "전력 인프라"],
    "keywords": ["Bloom Energy", "Oracle", "LS ELECTRIC", "연료전지", "배전반", "데이터센터"],
    "sentiment": "bull",
    "source_ids": ["msg1", "msg2", "msg3", "msg4"]
  },
  {
    "title": "현대차그룹 실적 부진 우려",
    "summary": "현대차 1분기 영업이익 컨센서스 하회 전망. 기아 미국 시장 판매 감소 및 SUV 재고 증가로 수익성 압박",
    "themes": ["자동차 실적 부진", "재고 증가"],
    "keywords": ["현대차", "기아", "SUV"],
    "sentiment": "bear",
    "source_ids": ["msg5", "msg6"]
  }
]
```

**핵심 포인트**:
- Bloom Energy 관련 3개 메시지를 하나의 이슈로 통합 (중복 방지)
- LS ELECTRIC도 같은 테마(전력 인프라)에 포함
- 현대차/기아는 별도 이슈 (다른 테마)
"""


MAP_EXAMPLE_2 = """
**입력 메시지**:
```
[msg1] 삼성전자 HBM3E 엔비디아 검증 통과 임박
[msg2] SK하이닉스 HBM3E 12단 양산 시작
[msg3] 마이크론 HBM3E 가격 20% 인상 발표
```

**출력**:
```json
[
  {
    "title": "HBM 메모리 공급 부족 심화",
    "summary": "삼성전자 엔비디아 검증 통과 임박, SK하이닉스 12단 양산 개시. 마이크론 가격 20% 인상으로 공급 부족 가시화",
    "themes": ["AI 메모리 업사이클", "HBM 공급 부족"],
    "keywords": ["삼성전자", "SK하이닉스", "마이크론", "HBM3E", "엔비디아"],
    "sentiment": "bull",
    "source_ids": ["msg1", "msg2", "msg3"]
  }
]
```

**핵심 포인트**:
- 3개 메시지가 모두 HBM 주제 → 하나의 이슈로 통합
- 테마는 "반도체" (X) → "AI 메모리 업사이클" (O) - 구체적
"""


def get_map_examples() -> str:
    """프롬프트용 포맷팅된 Map 예시 반환."""
    return f"{MAP_EXAMPLE_1}\n\n{MAP_EXAMPLE_2}"
```

- [ ] **Step 3: Shuffle 예시 생성**

`src/pipelines/daily_report/examples/shuffle_examples.py` 생성:

```python
"""Shuffle stage용 Few-shot 예시."""

SHUFFLE_EXAMPLE_1 = """
**입력 테마 리스트**:
```json
[
  "AI 전력 인프라",
  "데이터센터 파워",
  "AI DC 전력",
  "전력 인프라 투자",
  "반도체 업사이클",
  "메모리 가격 인상",
  "DRAM 상승",
  "HBM 공급 부족",
  "자동차 실적",
  "현대차 부진"
]
```

**출력**:
```json
{
  "AI 데이터센터 전력 인프라": [
    "AI 전력 인프라",
    "데이터센터 파워",
    "AI DC 전력",
    "전력 인프라 투자"
  ],
  "AI 메모리 업사이클": [
    "반도체 업사이클",
    "메모리 가격 인상",
    "DRAM 상승",
    "HBM 공급 부족"
  ],
  "자동차 실적 부진": [
    "자동차 실적",
    "현대차 부진"
  ]
}
```

**핵심 포인트**:
- 4개의 전력 관련 테마 → "AI 데이터센터 전력 인프라"로 통합
- 4개의 메모리 관련 테마 → "AI 메모리 업사이클"로 통합
- 너무 광범위하게 묶지 않음 (전력과 메모리는 분리)
"""


def get_shuffle_examples() -> str:
    """프롬프트용 포맷팅된 Shuffle 예시 반환."""
    return SHUFFLE_EXAMPLE_1
```

- [ ] **Step 4: Reduce 예시 생성**

`src/pipelines/daily_report/examples/reduce_examples.py` 생성:

```python
"""Reduce stage용 Few-shot 예시."""

REDUCE_EXAMPLE_1 = """
**테마**: AI 데이터센터 전력 인프라

**관련 이슈들**:
- Oracle-Bloom Energy 2.8GW 연료전지 계약
- LS ELECTRIC 북미 배전반 1,700억원 수주
- 2030년 DC 전력 수요 1,350TWh 전망

**관련 뉴스**:
- Bloom Energy CEO: "AI 인프라 전력 수요 폭발적 증가"
- 한국 전력기기 3사 북미 수주 가시화

**출력**:
```json
{
  "theme": "AI 데이터센터 전력 인프라",
  "emoji": "⚡",
  "summary": "🔋 Oracle-Bloom Energy 2.8GW 연료전지 계약 체결\n📈 LS ELECTRIC 북미 AI DC 배전반 1,700억원 수주\n⚡ 2030년 DC 전력 수요 1,350TWh 전망 (+220%)\n🌐 한국 전력기기 3사 북미 진출 본격화",
  "impact": "전력 인프라 병목 해소로 AI 투자 가속화. 한국 전력기기 기업들의 글로벌 수주 레벨업 기대. Bloom Energy-Oracle 파트너십은 청정 에너지 기반 AI 인프라 확산의 신호탄",
  "stocks": [
    {
      "name": "LS ELECTRIC",
      "ticker": "010120.KS",
      "catalyst": "북미 AI 데이터센터 배전반 1,700억원 공급 계약 체결"
    }
  ]
}
```

**핵심 포인트**:
- Summary에 이모지 적절히 사용 (🔋⚡📈🌐)
- Bullet point 형식으로 가독성 확보
- Impact는 시장 영향 + 투자 시사점 포함
- 관련 종목은 촉매 뉴스와 함께 명시
"""


def get_reduce_examples() -> str:
    """프롬프트용 포맷팅된 Reduce 예시 반환."""
    return REDUCE_EXAMPLE_1
```

- [ ] **Step 5: 프롬프트 인프라 커밋**

```bash
git add src/pipelines/daily_report/prompts.py src/pipelines/daily_report/examples/
git commit -m "feat(daily_report): 버전 관리가 포함된 프롬프트 인프라 추가

프롬프트 파일:
- prompts.py: V1/V2 버전 관리 지원하는 모든 프롬프트
- examples/: 실제 2026-04-14 데이터 기반 few-shot 예시

Map 예시: Bloom Energy 클러스터링 케이스 (4개 메시지 → 1개 이슈)
Shuffle 예시: 테마 정규화 (4개 변형 → 1개 정규화명)
Reduce 예시: 이모지, bullet points, Impact 포함 한글 스타일

설계: 프롬프트는 버전 관리, git 커밋으로 평가 결과 추적"
```

---

## Task 4: Map Stage (테마 추출)

**파일:**
- 생성: `src/pipelines/daily_report/stages/map_stage.py`
- 생성: `tests/pipelines/daily_report/test_map_stage.py`

- [ ] **Step 1: Map stage 구현 작성**

`src/pipelines/daily_report/stages/map_stage.py` 생성:

```python
"""Map stage: 텔레그램 메시지에서 테마를 가진 이슈 추출."""
import asyncio
import json
from typing import List
from pathlib import Path
from langchain_core.messages import HumanMessage
from src.llm.provider import LLMProvider
from src.pipelines.daily_report.models import TelegramMessage, MappedIssue
from src.pipelines.daily_report.prompts import MAP_PROMPT
from src.pipelines.daily_report.examples.map_examples import get_map_examples


def map_stage(
    messages: List[TelegramMessage],
    max_tokens_per_chunk: int = 6000,
) -> List[MappedIssue]:
    """
    청크 단위로 텔레그램 메시지에서 이슈 추출.
    
    Args:
        messages: 텔레그램 메시지 리스트
        max_tokens_per_chunk: 청크당 최대 토큰 수 (대략)
    
    Returns:
        테마를 가진 MappedIssue 리스트
    """
    if not messages:
        return []
    
    chunks = _chunk_messages(messages, max_tokens_per_chunk)
    
    # 청크를 병렬로 처리
    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(_analyze_chunks_parallel(chunks))
    
    # 결과 flatten
    all_issues = []
    for chunk_issues in results:
        all_issues.extend(chunk_issues)
    
    return all_issues


def _chunk_messages(
    messages: List[TelegramMessage],
    max_tokens: int,
) -> List[List[TelegramMessage]]:
    """
    토큰 추정치 기반으로 메시지를 청크로 분할.
    
    대략적인 추정: 한글 1자 ≈ 2 토큰, 영어 1단어 ≈ 1.3 토큰
    """
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for msg in messages:
        # 대략적인 토큰 추정
        msg_tokens = len(msg.text) * 2  # 보수적 추정
        
        if current_tokens + msg_tokens > max_tokens and current_chunk:
            # 새 청크 시작
            chunks.append(current_chunk)
            current_chunk = [msg]
            current_tokens = msg_tokens
        else:
            current_chunk.append(msg)
            current_tokens += msg_tokens
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


async def _analyze_chunks_parallel(
    chunks: List[List[TelegramMessage]],
) -> List[List[MappedIssue]]:
    """asyncio로 청크를 병렬 분석."""
    llm = LLMProvider.create(provider="openai", model="gpt-4o", temperature=0.3)
    
    tasks = [_analyze_chunk(chunk, llm) for chunk in chunks]
    return await asyncio.gather(*tasks)


async def _analyze_chunk(
    chunk: List[TelegramMessage],
    llm,
) -> List[MappedIssue]:
    """LLM으로 단일 청크 분석."""
    # 프롬프트용 메시지 포맷팅
    messages_text = "\n".join([
        f"[{msg.message_id}] {msg.text}"
        for msg in chunk
    ])
    
    # 프롬프트 구성
    prompt = MAP_PROMPT.format(
        examples=get_map_examples(),
        messages=messages_text,
    )
    
    # LLM 호출
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    
    # JSON 응답 파싱
    try:
        # 응답에서 JSON 추출 (마크다운 코드 블록 처리)
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        issues_data = json.loads(content)
        return [MappedIssue(**issue) for issue in issues_data]
    except Exception as e:
        print(f"⚠️  LLM 응답 파싱 실패: {e}")
        print(f"응답: {response.content[:200]}...")
        return []


# 테스트용 CLI 진입점
if __name__ == "__main__":
    import sys
    from src.pipelines.daily_report.stages.ingest_stage import ingest
    
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-14"
    
    # 데이터 로드
    ingest_result = ingest(date)
    print(f"✓ {len(ingest_result.messages)}개 메시지 로드")
    
    # Map stage 실행
    issues = map_stage(ingest_result.messages)
    print(f"✓ {len(issues)}개 이슈 추출")
    
    # 요약 출력
    total_themes = sum(len(issue.themes) for issue in issues)
    unique_themes = len(set(theme for issue in issues for theme in issue.themes))
    avg_sources = sum(len(issue.source_ids) for issue in issues) / len(issues) if issues else 0
    
    print(f"✓ 테마: {total_themes}개 총, {unique_themes}개 고유")
    print(f"✓ 이슈당 평균 소스 수: {avg_sources:.1f}")
    
    # 출력 저장
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/map_{date}.json"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump([issue.model_dump() for issue in issues], f, ensure_ascii=False, indent=2)
    print(f"✓ {output_file}에 저장")
```

- [ ] **Step 2: Map stage 테스트 작성**

`tests/pipelines/daily_report/test_map_stage.py` 생성:

```python
"""Map stage 테스트."""
import pytest
from src.pipelines.daily_report.stages.map_stage import (
    map_stage,
    _chunk_messages,
)


def test_chunk_messages_respects_max_tokens(sample_messages):
    """_chunk_messages가 토큰 제한을 지키는지 테스트."""
    # 작은 청크 강제
    chunks = _chunk_messages(sample_messages, max_tokens=100)
    
    # 여러 청크가 생성되어야 함
    assert len(chunks) > 1
    
    # 각 청크는 제한 내여야 함 (대략 체크)
    for chunk in chunks:
        total_chars = sum(len(msg.text) for msg in chunk)
        assert total_chars * 2 <= 150  # 약간의 여유 허용


def test_map_stage_with_sample_messages(sample_messages):
    """샘플 메시지로 Map stage 테스트."""
    issues = map_stage(sample_messages)
    
    # 최소 1개 이슈 추출되어야 함
    assert len(issues) >= 1
    
    # 구조 검증
    for issue in issues:
        assert issue.title  # 제목 존재
        assert 1 <= len(issue.themes) <= 3  # 1-3개 테마
        assert issue.sentiment in ["bull", "bear", "neutral"]
        assert len(issue.source_ids) > 0  # 소스 참조 존재


@pytest.mark.integration
def test_map_stage_with_real_data():
    """실제 2026-04-14 데이터로 통합 테스트."""
    from src.pipelines.daily_report.stages.ingest_stage import ingest
    
    ingest_result = ingest("2026-04-14")
    issues = map_stage(ingest_result.messages)
    
    # 실제 데이터는 이슈를 생성해야 함
    assert len(issues) > 0
    
    # 클러스터링 품질 체크
    avg_sources = sum(len(issue.source_ids) for issue in issues) / len(issues)
    assert avg_sources >= 3  # 이슈당 여러 메시지 클러스터링되어야 함
    
    # 테마 다양성 체크
    unique_themes = len(set(theme for issue in issues for theme in issue.themes))
    assert 5 <= unique_themes <= 30  # 합리적인 범위
```

- [ ] **Step 3: Map 테스트 실행**

```bash
uv run pytest tests/pipelines/daily_report/test_map_stage.py -v -m "not integration"
```

예상 결과: Unit 테스트 통과

- [ ] **Step 4: Map 통합 테스트 실행**

```bash
uv run pytest tests/pipelines/daily_report/test_map_stage.py -v -m integration
```

예상 결과: 통합 테스트 통과, 메트릭 출력

- [ ] **Step 5: Map CLI 수동 테스트**

```bash
python -m src.pipelines.daily_report.stages.map_stage 2026-04-14
```

예상 결과: 
- 이슈 개수, 테마 통계 출력
- `tests/pipelines/daily_report/fixtures/stage_outputs/map_2026-04-14.json` 저장
- 수동으로 출력 품질 검사

- [ ] **Step 6: Map 출력 품질 평가**

`map_2026-04-14.json` 수동 검토:
- 유사 메시지가 단일 이슈로 클러스터링되었나?
- 테마가 의미론적인가 (섹터 태그가 아닌)?
- 키워드가 관련성 있나 (종목명, 기술용어)?
- 품질이 낮으면 prompts.py의 MAP_PROMPT 개선

- [ ] **Step 7: Map stage 커밋**

```bash
git add src/pipelines/daily_report/stages/map_stage.py tests/pipelines/daily_report/test_map_stage.py
git commit -m "feat(daily_report): 테마 추출용 Map stage 추가

- 토큰 제한으로 메시지 청크 분할 (기본 6000)
- gpt-4o로 병렬 비동기 처리 (temp=0.3)
- 이슈당 1-3개 테마를 가진 MappedIssue 추출
- CLI: python -m src.pipelines.daily_report.stages.map_stage <date>
- 테스트: 청크 로직, 실제 데이터 통합 테스트

메트릭 (2026-04-14):
- Y개 메시지에서 X개 이슈 (이슈당 평균 Z개 소스)
- B개 총 테마 태그에서 A개 고유 테마"
```

---

## Task 5: Shuffle Stage (테마 정규화)

**파일:**
- 생성: `src/pipelines/daily_report/stages/shuffle_stage.py`
- 생성: `tests/pipelines/daily_report/test_shuffle_stage.py`

- [ ] **Step 1: Shuffle stage 구현 작성**

`src/pipelines/daily_report/stages/shuffle_stage.py` 생성:

```python
"""Shuffle stage: 청크 간 테마 정규화."""
import json
from typing import List, Dict, Set
from pathlib import Path
from collections import defaultdict
from langchain_core.messages import HumanMessage
from src.llm.provider import LLMProvider
from src.pipelines.daily_report.models import MappedIssue, ShuffleResult
from src.pipelines.daily_report.prompts import SHUFFLE_PROMPT
from src.pipelines.daily_report.examples.shuffle_examples import get_shuffle_examples


def shuffle_stage(issues: List[MappedIssue]) -> ShuffleResult:
    """
    테마를 정규화하고 정규화 테마별로 이슈 그룹핑.
    
    Args:
        issues: Map stage의 MappedIssue 리스트
    
    Returns:
        정규화 테마 및 그룹핑된 이슈를 가진 ShuffleResult
    """
    if not issues:
        return ShuffleResult(canonical_themes={}, theme_groups={})
    
    # 모든 고유 테마 수집
    unique_themes = _collect_unique_themes(issues)
    
    if len(unique_themes) == 0:
        return ShuffleResult(canonical_themes={}, theme_groups={})
    
    # LLM으로 테마 정규화
    canonical_mapping = _normalize_themes(unique_themes)
    
    # 이슈에 매핑 적용 및 그룹핑
    theme_groups = _group_issues_by_canonical_theme(issues, canonical_mapping)
    
    return ShuffleResult(
        canonical_themes=canonical_mapping,
        theme_groups=theme_groups,
    )


def _collect_unique_themes(issues: List[MappedIssue]) -> Set[str]:
    """이슈에서 모든 고유 테마명 수집."""
    themes = set()
    for issue in issues:
        themes.update(issue.themes)
    return themes


def _normalize_themes(themes: Set[str]) -> Dict[str, List[str]]:
    """
    LLM으로 테마 정규화.
    
    Returns:
        정규화 테마명 → 원본 테마명 리스트 매핑 Dict
    """
    llm = LLMProvider.create(provider="openai", model="gpt-4o", temperature=0.1)
    
    # 프롬프트 구성
    themes_json = json.dumps(list(themes), ensure_ascii=False, indent=2)
    prompt = SHUFFLE_PROMPT.format(
        examples=get_shuffle_examples(),
        themes=themes_json,
    )
    
    # LLM 호출
    response = llm.invoke([HumanMessage(content=prompt)])
    
    # JSON 응답 파싱
    try:
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        canonical_mapping = json.loads(content)
        return canonical_mapping
    except Exception as e:
        print(f"⚠️  LLM 응답 파싱 실패: {e}")
        print(f"응답: {response.content[:200]}...")
        # Fallback: identity 매핑
        return {theme: [theme] for theme in themes}


def _group_issues_by_canonical_theme(
    issues: List[MappedIssue],
    canonical_mapping: Dict[str, List[str]],
) -> Dict[str, List[MappedIssue]]:
    """
    정규화 테마명별로 이슈 그룹핑.
    
    역매핑 구성 (원본 → 정규화), 그 후 이슈 그룹핑.
    """
    # 역매핑 구성
    original_to_canonical = {}
    for canonical, originals in canonical_mapping.items():
        for original in originals:
            original_to_canonical[original] = canonical
    
    # 이슈 그룹핑
    theme_groups = defaultdict(list)
    for issue in issues:
        # 각 이슈는 여러 테마를 가질 수 있음
        # 이슈를 모든 정규화 테마 그룹에 추가
        for theme in issue.themes:
            canonical = original_to_canonical.get(theme, theme)
            if issue not in theme_groups[canonical]:
                theme_groups[canonical].append(issue)
    
    return dict(theme_groups)


# 테스트용 CLI 진입점
if __name__ == "__main__":
    import sys
    
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-14"
    
    # Map 출력 로드
    input_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/map_{date}.json"
    with open(input_file, "r", encoding="utf-8") as f:
        issues_data = json.load(f)
        issues = [MappedIssue(**issue) for issue in issues_data]
    
    print(f"✓ {len(issues)}개 이슈 로드")
    
    # Shuffle stage 실행
    result = shuffle_stage(issues)
    
    print(f"✓ {len(result.canonical_themes)}개 정규화 테마")
    print(f"✓ 테마 그룹: {len(result.theme_groups)}개")
    
    # 정규화 요약 출력
    original_count = sum(len(originals) for originals in result.canonical_themes.values())
    normalization_rate = len(result.canonical_themes) / original_count if original_count > 0 else 0
    print(f"✓ 정규화 비율: {normalization_rate:.2f} ({len(result.canonical_themes)}/{original_count})")
    
    # 테마 그룹 출력
    print("\n## 테마 그룹:")
    for canonical, group_issues in result.theme_groups.items():
        print(f"  - {canonical}: {len(group_issues)}개 이슈")
    
    # 출력 저장
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/shuffle_{date}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)
    print(f"\n✓ {output_file}에 저장")
```

- [ ] **Step 2: Shuffle stage 테스트 작성**

`tests/pipelines/daily_report/test_shuffle_stage.py` 생성:

```python
"""Shuffle stage 테스트."""
import pytest
from src.pipelines.daily_report.stages.shuffle_stage import (
    shuffle_stage,
    _collect_unique_themes,
    _group_issues_by_canonical_theme,
)
from src.pipelines.daily_report.models import MappedIssue


def test_collect_unique_themes():
    """_collect_unique_themes가 모든 고유 테마를 추출하는지 테스트."""
    issues = [
        MappedIssue(
            title="이슈1",
            summary="요약",
            themes=["AI 전력", "데이터센터"],
            keywords=[],
            sentiment="bull",
            source_ids=[],
        ),
        MappedIssue(
            title="이슈2",
            summary="요약",
            themes=["AI 전력", "반도체"],
            keywords=[],
            sentiment="bull",
            source_ids=[],
        ),
    ]
    
    themes = _collect_unique_themes(issues)
    assert themes == {"AI 전력", "데이터센터", "반도체"}


def test_group_issues_by_canonical_theme():
    """_group_issues_by_canonical_theme이 올바르게 그룹핑하는지 테스트."""
    issues = [
        MappedIssue(
            title="이슈1",
            summary="요약",
            themes=["AI 전력", "데이터센터 파워"],
            keywords=[],
            sentiment="bull",
            source_ids=["msg1"],
        ),
        MappedIssue(
            title="이슈2",
            summary="요약",
            themes=["반도체"],
            keywords=[],
            sentiment="bull",
            source_ids=["msg2"],
        ),
    ]
    
    canonical_mapping = {
        "AI 데이터센터 전력": ["AI 전력", "데이터센터 파워"],
        "반도체": ["반도체"],
    }
    
    groups = _group_issues_by_canonical_theme(issues, canonical_mapping)
    
    assert len(groups) == 2
    assert len(groups["AI 데이터센터 전력"]) == 1
    assert len(groups["반도체"]) == 1


@pytest.mark.integration
def test_shuffle_stage_with_real_data():
    """실제 Map 출력으로 통합 테스트."""
    import json
    
    # Map 출력 로드
    with open("tests/pipelines/daily_report/fixtures/stage_outputs/map_2026-04-14.json", "r") as f:
        issues_data = json.load(f)
        issues = [MappedIssue(**issue) for issue in issues_data]
    
    result = shuffle_stage(issues)
    
    # 테마를 정규화해야 함
    assert len(result.canonical_themes) > 0
    original_count = sum(len(v) for v in result.canonical_themes.values())
    assert len(result.canonical_themes) < original_count  # 일부 정규화 발생
    
    # 이슈를 그룹핑해야 함
    assert len(result.theme_groups) == len(result.canonical_themes)
    
    # 정규화 비율 체크
    rate = len(result.canonical_themes) / original_count
    assert 0.3 <= rate <= 0.9  # 합리적인 정규화
```

- [ ] **Step 3: Shuffle 테스트 실행**

```bash
uv run pytest tests/pipelines/daily_report/test_shuffle_stage.py -v -m "not integration"
```

예상 결과: Unit 테스트 통과

- [ ] **Step 4: Shuffle 통합 테스트 실행**

```bash
uv run pytest tests/pipelines/daily_report/test_shuffle_stage.py -v -m integration
```

예상 결과: 통합 테스트 통과, 정규화 발생

- [ ] **Step 5: Shuffle CLI 수동 테스트**

```bash
python -m src.pipelines.daily_report.stages.shuffle_stage 2026-04-14
```

예상 결과:
- 정규화 통계 출력
- 테마 그룹 리스트
- `shuffle_2026-04-14.json` 저장

- [ ] **Step 6: Shuffle 출력 품질 평가**

`shuffle_2026-04-14.json` 수동 검토:
- 유사 테마가 제대로 정규화되었나?
- 테마 그룹이 의미론적으로 일관성 있나?
- 정규화 비율이 합리적인가 (0.3-0.7)?
- 품질이 낮으면 SHUFFLE_PROMPT 개선

- [ ] **Step 7: Shuffle stage 커밋**

```bash
git add src/pipelines/daily_report/stages/shuffle_stage.py tests/pipelines/daily_report/test_shuffle_stage.py
git commit -m "feat(daily_report): 테마 정규화용 Shuffle stage 추가

- 모든 MappedIssue에서 고유 테마 수집
- gpt-4o 기반 LLM 클러스터링 (temp=0.1)
- 정규화 테마명별로 이슈 그룹핑
- CLI: python -m src.pipelines.daily_report.stages.shuffle_stage <date>
- 테스트: 테마 수집, 그룹핑 로직, 통합 테스트

메트릭 (2026-04-14):
- X개 원본 테마 → Y개 정규화 테마 (비율: Z)
- A개 테마 그룹 생성"
```

---

## Task 6: Reduce Stage (테마별 분석 - ddgs + gpt-5.2)

**파일:**
- 생성: `src/pipelines/daily_report/stages/reduce_stage.py`
- 생성: `tests/pipelines/daily_report/test_reduce_stage.py`

- [ ] **Step 1: Reduce stage 구현 작성**

`src/pipelines/daily_report/stages/reduce_stage.py` 생성:

```python
"""Reduce stage: 테마별 분석 (ddgs 뉴스 + gpt-5.2)."""
import asyncio
import json
from typing import List, Dict
from pathlib import Path
from duckduckgo_search import DDGS
from langchain_core.messages import HumanMessage
from src.llm.provider import LLMProvider
from src.pipelines.daily_report.models import ShuffleResult, MappedIssue, NewsItem
from src.pipelines.daily_report.prompts import REDUCE_PROMPT
from src.pipelines.daily_report.examples.reduce_examples import get_reduce_examples


def reduce_stage(shuffle_result: ShuffleResult) -> List[NewsItem]:
    """
    각 정규화 테마에 대한 NewsItem 생성.
    
    Args:
        shuffle_result: Shuffle stage 출력
    
    Returns:
        테마별 분석 NewsItem 리스트
    """
    if not shuffle_result.theme_groups:
        return []
    
    # 테마별로 병렬 처리
    loop = asyncio.get_event_loop()
    news_items = loop.run_until_complete(
        _analyze_themes_parallel(shuffle_result.theme_groups)
    )
    
    return news_items


async def _analyze_themes_parallel(
    theme_groups: Dict[str, List[MappedIssue]],
) -> List[NewsItem]:
    """asyncio로 테마를 병렬 분석."""
    llm = LLMProvider.create(provider="openai", model="gpt-5.2", temperature=0.5)
    
    tasks = [
        _analyze_theme(theme, issues, llm)
        for theme, issues in theme_groups.items()
    ]
    return await asyncio.gather(*tasks)


async def _analyze_theme(
    theme: str,
    issues: List[MappedIssue],
    llm,
) -> NewsItem:
    """LLM으로 단일 테마 분석."""
    # 이슈에서 키워드 수집
    keywords = set()
    for issue in issues:
        keywords.update(issue.keywords)
    keywords = list(keywords)
    
    # ddgs로 뉴스 검색
    news_articles = _search_news(keywords)
    
    # 프롬프트용 이슈 포맷팅
    issues_text = "\n\n".join([
        f"**{issue.title}**\n{issue.summary}\n감성: {issue.sentiment}\n키워드: {', '.join(issue.keywords)}"
        for issue in issues
    ])
    
    # 프롬프트용 뉴스 포맷팅
    news_text = "\n\n".join([
        f"- {article['title']}\n  {article['snippet']}"
        for article in news_articles[:5]  # 상위 5개만
    ])
    
    # 프롬프트 구성
    prompt = REDUCE_PROMPT.format(
        theme=theme,
        issues=issues_text,
        news_articles=news_text if news_text else "(관련 뉴스 없음)",
        examples=get_reduce_examples(),
    )
    
    # LLM 호출
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    
    # JSON 응답 파싱
    try:
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        news_item_data = json.loads(content)
        return NewsItem(**news_item_data)
    except Exception as e:
        print(f"⚠️  테마 '{theme}' LLM 응답 파싱 실패: {e}")
        print(f"응답: {response.content[:200]}...")
        # Fallback: 기본 NewsItem
        return NewsItem(
            theme=theme,
            emoji="ℹ️",
            summary=f"- {issues[0].title}" if issues else "- 정보 없음",
            impact="분석 실패",
        )


def _search_news(keywords: List[str]) -> List[Dict]:
    """
    ddgs로 뉴스 검색.
    
    Returns:
        뉴스 기사 리스트 (title, snippet, url)
    """
    if not keywords:
        return []
    
    # 키워드를 쿼리로 결합
    query = " ".join(keywords[:3])  # 상위 3개 키워드만
    
    try:
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=10))
            return [
                {
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("url", ""),
                }
                for r in results
            ]
    except Exception as e:
        print(f"⚠️  ddgs 뉴스 검색 실패 ('{query}'): {e}")
        return []


# 테스트용 CLI 진입점
if __name__ == "__main__":
    import sys
    
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-14"
    
    # Shuffle 출력 로드
    input_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/shuffle_{date}.json"
    with open(input_file, "r", encoding="utf-8") as f:
        shuffle_data = json.load(f)
        shuffle_result = ShuffleResult(**shuffle_data)
    
    print(f"✓ {len(shuffle_result.theme_groups)}개 테마 그룹 로드")
    
    # Reduce stage 실행
    news_items = reduce_stage(shuffle_result)
    print(f"✓ {len(news_items)}개 NewsItem 생성")
    
    # 품질 체크
    with_impact = sum(1 for item in news_items if item.impact)
    with_emoji = sum(1 for item in news_items if item.emoji)
    with_stocks = sum(1 for item in news_items if item.stocks)
    
    print(f"✓ Impact 있음: {with_impact}/{len(news_items)}")
    print(f"✓ Emoji 있음: {with_emoji}/{len(news_items)}")
    print(f"✓ 종목 있음: {with_stocks}/{len(news_items)}")
    
    # 출력 저장
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/reduce_{date}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump([item.model_dump() for item in news_items], f, ensure_ascii=False, indent=2)
    print(f"✓ {output_file}에 저장")
```

- [ ] **Step 2: Reduce stage 테스트 작성**

`tests/pipelines/daily_report/test_reduce_stage.py` 생성:

```python
"""Reduce stage 테스트."""
import pytest
from unittest.mock import patch
from src.pipelines.daily_report.stages.reduce_stage import (
    reduce_stage,
    _search_news,
)


@patch("src.pipelines.daily_report.stages.reduce_stage.DDGS")
def test_search_news_with_keywords(mock_ddgs):
    """_search_news가 ddgs로 검색하는지 테스트."""
    # Mock ddgs 응답
    mock_ddgs.return_value.__enter__.return_value.news.return_value = [
        {"title": "테스트 뉴스", "body": "내용", "url": "http://example.com"}
    ]
    
    results = _search_news(["Bloom Energy", "Oracle"])
    
    assert len(results) == 1
    assert results[0]["title"] == "테스트 뉴스"


@pytest.mark.integration
def test_reduce_stage_with_real_data():
    """실제 Shuffle 출력으로 통합 테스트."""
    import json
    from src.pipelines.daily_report.models import ShuffleResult
    
    # Shuffle 출력 로드
    with open("tests/pipelines/daily_report/fixtures/stage_outputs/shuffle_2026-04-14.json", "r") as f:
        shuffle_data = json.load(f)
        shuffle_result = ShuffleResult(**shuffle_data)
    
    news_items = reduce_stage(shuffle_result)
    
    # NewsItem 생성되어야 함
    assert len(news_items) > 0
    
    # 품질 체크
    for item in news_items:
        assert item.theme  # 테마 있음
        assert item.emoji  # 이모지 있음
        assert item.summary  # 요약 있음
        assert item.impact  # Impact 있음
        assert item.emoji in "🚀📈⚠️ℹ️📉⚡"  # 유효한 이모지
```

- [ ] **Step 3: Reduce 테스트 실행**

```bash
uv run pytest tests/pipelines/daily_report/test_reduce_stage.py -v -m "not integration"
```

예상 결과: Unit 테스트 통과

- [ ] **Step 4: Reduce 통합 테스트 실행**

```bash
uv run pytest tests/pipelines/daily_report/test_reduce_stage.py -v -m integration
```

예상 결과: 통합 테스트 통과 (실제 ddgs 호출, 시간 소요)

- [ ] **Step 5: Reduce CLI 수동 테스트**

```bash
python -m src.pipelines.daily_report.stages.reduce_stage 2026-04-14
```

예상 결과:
- NewsItem 개수 출력
- 품질 메트릭 (Impact, Emoji, 종목)
- `reduce_2026-04-14.json` 저장

- [ ] **Step 6: Reduce 출력 품질 평가**

`reduce_2026-04-14.json` 수동 검토:
- 한글이 유창한가?
- 이모지가 적절한가?
- Impact 문구가 의미 있나?
- Bullet point 형식이 제대로인가?
- 품질이 낮으면 REDUCE_PROMPT 개선

- [ ] **Step 7: Reduce stage 커밋**

```bash
git add src/pipelines/daily_report/stages/reduce_stage.py tests/pipelines/daily_report/test_reduce_stage.py
git commit -m "feat(daily_report): ddgs + gpt-5.2로 Reduce stage 추가

- 테마별 키워드로 ddgs 뉴스 검색
- gpt-5.2로 한글 분석 생성 (temp=0.5)
- NewsItem: 이모지, bullet points, Impact 문구
- 테마별 병렬 비동기 처리
- CLI: python -m src.pipelines.daily_report.stages.reduce_stage <date>
- 테스트: ddgs 모킹, 통합 테스트

메트릭 (2026-04-14):
- X개 NewsItem 생성
- Impact: Y%, Emoji: Z%, 종목: A%"
```

---

## Task 7: Wrapup Stage (크로스 테마 인사이트 - gpt-5.2)

**파일:**
- 생성: `src/pipelines/daily_report/stages/wrapup_stage.py`
- 생성: `tests/pipelines/daily_report/test_wrapup_stage.py`

- [ ] **Step 1: Wrapup stage 구현 작성**

`src/pipelines/daily_report/stages/wrapup_stage.py` 생성:

```python
"""Wrapup stage: 크로스 테마 인사이트 (gpt-5.2)."""
import json
from typing import List
from pathlib import Path
from langchain_core.messages import HumanMessage
from src.llm.provider import LLMProvider
from src.pipelines.daily_report.models import NewsItem
from src.pipelines.daily_report.prompts import WRAPUP_PROMPT


def wrapup_stage(news_items: List[NewsItem]) -> List[str]:
    """
    여러 테마를 연결하는 메타 인사이트 생성.
    
    Args:
        news_items: Reduce stage의 NewsItem 리스트
    
    Returns:
        크로스 테마 인사이트 문자열 리스트
    """
    if not news_items:
        return []
    
    insights = _synthesize_insights(news_items)
    return insights


def _synthesize_insights(news_items: List[NewsItem]) -> List[str]:
    """LLM으로 인사이트 합성."""
    llm = LLMProvider.create(provider="openai", model="gpt-5.2", temperature=0.7)
    
    # 프롬프트용 NewsItem 포맷팅
    news_text = "\n\n".join([
        f"## {item.emoji} {item.theme}\n{item.summary}\n\n**Impact:** {item.impact}"
        for item in news_items
    ])
    
    # 프롬프트 구성
    prompt = WRAPUP_PROMPT.format(news_items=news_text)
    
    # LLM 호출
    response = llm.invoke([HumanMessage(content=prompt)])
    
    # JSON 응답 파싱
    try:
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        insights = json.loads(content)
        return insights
    except Exception as e:
        print(f"⚠️  LLM 응답 파싱 실패: {e}")
        print(f"응답: {response.content[:200]}...")
        # Fallback: 기본 인사이트
        return [f"ℹ️ {len(news_items)}개 테마 분석 완료"]


# 테스트용 CLI 진입점
if __name__ == "__main__":
    import sys
    
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-14"
    
    # Reduce 출력 로드
    input_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/reduce_{date}.json"
    with open(input_file, "r", encoding="utf-8") as f:
        news_data = json.load(f)
        news_items = [NewsItem(**item) for item in news_data]
    
    print(f"✓ {len(news_items)}개 NewsItem 로드")
    
    # Wrapup stage 실행
    insights = wrapup_stage(news_items)
    print(f"✓ {len(insights)}개 인사이트 생성")
    
    # 인사이트 출력
    print("\n## 크로스 테마 인사이트:")
    for idx, insight in enumerate(insights, 1):
        print(f"{idx}. {insight}")
    
    # 출력 저장
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/wrapup_{date}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(insights, f, ensure_ascii=False, indent=2)
    print(f"\n✓ {output_file}에 저장")
```

- [ ] **Step 2: Wrapup stage 테스트 작성**

`tests/pipelines/daily_report/test_wrapup_stage.py` 생성:

```python
"""Wrapup stage 테스트."""
import pytest
from src.pipelines.daily_report.stages.wrapup_stage import wrapup_stage
from src.pipelines.daily_report.models import NewsItem


def test_wrapup_stage_with_sample_news_items():
    """샘플 NewsItem으로 Wrapup stage 테스트."""
    news_items = [
        NewsItem(
            theme="AI 데이터센터 전력",
            emoji="⚡",
            summary="- 전력 인프라 투자",
            impact="AI 투자 가속화",
        ),
        NewsItem(
            theme="반도체 업사이클",
            emoji="🚀",
            summary="- HBM 공급 부족",
            impact="메모리 가격 상승",
        ),
    ]
    
    insights = wrapup_stage(news_items)
    
    # 인사이트 생성되어야 함
    assert len(insights) >= 1
    
    # 각 인사이트는 문자열
    for insight in insights:
        assert isinstance(insight, str)
        assert len(insight) > 10  # 최소 길이


@pytest.mark.integration
def test_wrapup_stage_with_real_data():
    """실제 Reduce 출력으로 통합 테스트."""
    import json
    
    # Reduce 출력 로드
    with open("tests/pipelines/daily_report/fixtures/stage_outputs/reduce_2026-04-14.json", "r") as f:
        news_data = json.load(f)
        news_items = [NewsItem(**item) for item in news_data]
    
    insights = wrapup_stage(news_items)
    
    # 인사이트 생성되어야 함
    assert 3 <= len(insights) <= 5  # 3-5개 목표
    
    # 품질 체크
    cross_theme_count = sum(1 for insight in insights if "+" in insight or "→" in insight)
    assert cross_theme_count >= len(insights) * 0.5  # 최소 50%가 크로스 테마
```

- [ ] **Step 3: Wrapup 테스트 실행**

```bash
uv run pytest tests/pipelines/daily_report/test_wrapup_stage.py -v -m "not integration"
```

예상 결과: Unit 테스트 통과

- [ ] **Step 4: Wrapup 통합 테스트 실행**

```bash
uv run pytest tests/pipelines/daily_report/test_wrapup_stage.py -v -m integration
```

예상 결과: 통합 테스트 통과

- [ ] **Step 5: Wrapup CLI 수동 테스트**

```bash
python -m src.pipelines.daily_report.stages.wrapup_stage 2026-04-14
```

예상 결과:
- 인사이트 개수 출력
- 인사이트 내용 출력
- `wrapup_2026-04-14.json` 저장

- [ ] **Step 6: Wrapup 출력 품질 평가**

`wrapup_2026-04-14.json` 수동 검토:
- 여러 테마를 연결하는가?
- 단순 요약이 아닌 새로운 시사점을 제공하는가?
- 이모지가 적절한가?
- 품질이 낮으면 WRAPUP_PROMPT 개선

- [ ] **Step 7: Wrapup stage 커밋**

```bash
git add src/pipelines/daily_report/stages/wrapup_stage.py tests/pipelines/daily_report/test_wrapup_stage.py
git commit -m "feat(daily_report): gpt-5.2로 Wrapup stage 추가

- 모든 NewsItem을 크로스 테마 인사이트로 합성
- gpt-5.2 사용 (temp=0.7 - 창의적 연결)
- 3-5개 인사이트 생성 목표
- CLI: python -m src.pipelines.daily_report.stages.wrapup_stage <date>
- 테스트: 샘플 데이터, 통합 테스트

메트릭 (2026-04-14):
- X개 인사이트 생성
- Y%가 크로스 테마 연결"
```

---

## Task 8: Renderer (마크다운 생성)

**파일:**
- 생성: `src/pipelines/daily_report/renderer.py`
- 생성: `tests/pipelines/daily_report/test_renderer.py`

- [ ] **Step 1: Renderer 구현 작성**

`src/pipelines/daily_report/renderer.py` 생성:

```python
"""Renderer: DailyReport를 마크다운으로 변환."""
from pathlib import Path
from src.pipelines.daily_report.models import DailyReport


def render_to_markdown(report: DailyReport) -> str:
    """
    DailyReport를 마크다운 문자열로 변환.
    
    Args:
        report: DailyReport 객체
    
    Returns:
        마크다운 문자열
    """
    lines = []
    
    # 제목
    lines.append(f"# Daily Report: {report.date}")
    lines.append("")
    
    # 매크로 스냅샷
    lines.append("## 📊 시장 스냅샷")
    lines.append("")
    
    # 미국 시장
    us = report.macro.us_markets
    lines.append(f"- 🇺🇸 미국: S&P500 {us.get('S&P500', 0):+.1f}%, "
                 f"나스닥 {us.get('NASDAQ', 0):+.1f}%, "
                 f"다우 {us.get('DOW', 0):+.1f}%")
    
    # 한국 시장
    kr = report.macro.kr_markets
    lines.append(f"- 🇰🇷 한국: KOSPI {kr.get('KOSPI', 0):+.1f}%, "
                 f"KOSDAQ {kr.get('KOSDAQ', 0):+.1f}%")
    
    # VIX, Fear & Greed
    lines.append(f"- 📉 VIX: {report.macro.vix:.1f}")
    
    fg = report.macro.fear_greed
    fg_label = "Extreme Fear" if fg < 25 else "Fear" if fg < 45 else "Neutral" if fg < 55 else "Greed" if fg < 75 else "Extreme Greed"
    lines.append(f"- 😨 Fear & Greed: {fg} ({fg_label})")
    
    # 환율
    lines.append(f"- 💰 원/달러: {report.macro.krw_usd:,.0f}원")
    lines.append("")
    
    # 크로스 테마 인사이트
    lines.append("## 🔥 오늘의 핵심 인사이트")
    lines.append("")
    for insight in report.insights:
        lines.append(f"- {insight}")
    lines.append("")
    
    # 테마별 분석
    lines.append("## 📰 테마별 분석")
    lines.append("")
    
    for item in report.news_items:
        lines.append(f"### {item.emoji} {item.theme}")
        lines.append("")
        lines.append(item.summary)
        lines.append("")
        lines.append(f"**(Impact: {item.impact})**")
        lines.append("")
        
        # 관련 종목
        if item.stocks:
            lines.append("**관련 종목:**")
            for stock in item.stocks:
                lines.append(f"- {stock.name} ({stock.ticker}): {stock.catalyst}")
            lines.append("")
    
    return "\n".join(lines)


def save_report(report: DailyReport, output_dir: str = "reports") -> str:
    """
    DailyReport를 마크다운 파일로 저장.
    
    Args:
        report: DailyReport 객체
        output_dir: 출력 디렉토리 루트
    
    Returns:
        저장된 파일 경로
    """
    # 날짜별 디렉토리 (reports/YYYY-MM/)
    date_obj = Path(report.date)
    year_month = report.date[:7]  # YYYY-MM
    output_path = Path(output_dir) / year_month / f"{report.date}_daily_report.md"
    
    # 디렉토리 생성
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 마크다운 생성 및 저장
    markdown = render_to_markdown(report)
    output_path.write_text(markdown, encoding="utf-8")
    
    return str(output_path)
```

- [ ] **Step 2: Renderer 테스트 작성**

`tests/pipelines/daily_report/test_renderer.py` 생성:

```python
"""Renderer 테스트."""
import pytest
from pathlib import Path
from src.pipelines.daily_report.renderer import render_to_markdown, save_report
from src.pipelines.daily_report.models import (
    DailyReport,
    MacroSnapshot,
    NewsItem,
)


def test_render_to_markdown(sample_macro):
    """render_to_markdown이 올바른 마크다운을 생성하는지 테스트."""
    report = DailyReport(
        date="2026-04-14",
        macro=sample_macro,
        insights=["🔥 테스트 인사이트"],
        news_items=[
            NewsItem(
                theme="테스트 테마",
                emoji="🚀",
                summary="- 테스트 내용",
                impact="테스트 영향",
            )
        ],
    )
    
    markdown = render_to_markdown(report)
    
    # 필수 섹션 포함 확인
    assert "# Daily Report: 2026-04-14" in markdown
    assert "## 📊 시장 스냅샷" in markdown
    assert "## 🔥 오늘의 핵심 인사이트" in markdown
    assert "## 📰 테마별 분석" in markdown
    assert "### 🚀 테스트 테마" in markdown
    assert "(Impact: 테스트 영향)" in markdown


def test_save_report(sample_macro, tmp_path):
    """save_report가 파일을 올바르게 저장하는지 테스트."""
    report = DailyReport(
        date="2026-04-14",
        macro=sample_macro,
        insights=["테스트"],
        news_items=[],
    )
    
    output_path = save_report(report, output_dir=str(tmp_path))
    
    # 파일 존재 확인
    assert Path(output_path).exists()
    
    # 경로 확인 (YYYY-MM/YYYY-MM-DD_daily_report.md)
    assert "2026-04" in output_path
    assert "2026-04-14_daily_report.md" in output_path
    
    # 내용 확인
    content = Path(output_path).read_text(encoding="utf-8")
    assert "# Daily Report: 2026-04-14" in content
```

- [ ] **Step 3: Renderer 테스트 실행**

```bash
uv run pytest tests/pipelines/daily_report/test_renderer.py -v
```

예상 결과: 모든 테스트 통과

- [ ] **Step 4: Renderer 커밋**

```bash
git add src/pipelines/daily_report/renderer.py tests/pipelines/daily_report/test_renderer.py
git commit -m "feat(daily_report): 마크다운 Renderer 추가

- DailyReport를 한글 마크다운으로 변환
- 섹션: 매크로 스냅샷, 인사이트, 테마별 분석
- reports/YYYY-MM/YYYY-MM-DD_daily_report.md에 저장
- 테스트: 마크다운 생성, 파일 저장"
```

---

## Task 9: Pipeline 통합 & CLI

**파일:**
- 생성: `src/pipelines/daily_report/pipeline.py`
- 수정: `src/pipelines/daily_report/__init__.py`
- 수정: `src/cli/main.py`
- 생성: `tests/pipelines/daily_report/test_pipeline.py`

- [ ] **Step 1: Pipeline 오케스트레이션 작성**

`src/pipelines/daily_report/pipeline.py` 생성:

```python
"""Daily report 파이프라인 오케스트레이션."""
from src.pipelines.daily_report.models import DailyReport
from src.pipelines.daily_report.stages.ingest_stage import ingest
from src.pipelines.daily_report.stages.map_stage import map_stage
from src.pipelines.daily_report.stages.shuffle_stage import shuffle_stage
from src.pipelines.daily_report.stages.reduce_stage import reduce_stage
from src.pipelines.daily_report.stages.wrapup_stage import wrapup_stage


def run_daily_report(date: str) -> DailyReport:
    """
    전체 daily report 파이프라인 실행.
    
    Args:
        date: 날짜 (YYYY-MM-DD)
    
    Returns:
        생성된 DailyReport
    
    Raises:
        FileNotFoundError: CSV가 없을 때
    """
    print(f"🔄 Daily Report 생성 중... ({date})")
    
    # Stage 1: Ingest
    print("  ⏳ Ingest: CSV 및 매크로 데이터 로드 중...")
    ingest_result = ingest(date)
    print(f"  ✓ Ingest: {len(ingest_result.messages)}개 메시지, 매크로 데이터 수집 완료")
    
    # Stage 2: Map
    print("  ⏳ Map: 이슈 추출 중...")
    issues = map_stage(ingest_result.messages)
    unique_themes = len(set(theme for issue in issues for theme in issue.themes))
    print(f"  ✓ Map: {len(issues)}개 이슈 추출 ({unique_themes}개 고유 테마)")
    
    # Stage 3: Shuffle
    print("  ⏳ Shuffle: 테마 정규화 중...")
    shuffle_result = shuffle_stage(issues)
    print(f"  ✓ Shuffle: {unique_themes}개 테마 → {len(shuffle_result.canonical_themes)}개 정규화 테마")
    
    # Stage 4: Reduce
    print("  ⏳ Reduce: 테마별 분석 중...")
    news_items = reduce_stage(shuffle_result)
    print(f"  ✓ Reduce: {len(news_items)}개 NewsItem 생성")
    
    # Stage 5: Wrapup
    print("  ⏳ Wrapup: 크로스 테마 인사이트 생성 중...")
    insights = wrapup_stage(news_items)
    print(f"  ✓ Wrapup: {len(insights)}개 인사이트 생성")
    
    # 최종 리포트 조립
    report = DailyReport(
        date=date,
        macro=ingest_result.macro,
        insights=insights,
        news_items=news_items,
    )
    
    print("✅ Daily Report 생성 완료")
    return report
```

- [ ] **Step 2: __init__.py 업데이트**

`src/pipelines/daily_report/__init__.py` 수정:

```python
"""Daily report 파이프라인."""
from src.pipelines.daily_report.pipeline import run_daily_report

__all__ = ["run_daily_report"]
```

- [ ] **Step 3: CLI 통합**

`src/cli/main.py`에 daily report 명령어 추가:

```python
@app.command()
def report(
    date: str = typer.Option(None, help="날짜 (YYYY-MM-DD), 기본값: 어제"),
    save: bool = typer.Option(True, help="파일 저장 여부"),
):
    """일일 시장 리포트 생성 (텔레그램 분석)."""
    from datetime import datetime, timedelta
    from src.pipelines.daily_report import run_daily_report
    from src.pipelines.daily_report.renderer import render_to_markdown, save_report
    from rich.panel import Panel
    
    # 기본값: 어제
    if not date:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    try:
        # 파이프라인 실행
        report = run_daily_report(date)
        
        # 콘솔 출력
        console.print(Panel("📊 시장 스냅샷", style="bold blue"))
        console.print(f"🇺🇸 미국: S&P500 {report.macro.us_markets.get('S&P500', 0):+.1f}%, "
                     f"나스닥 {report.macro.us_markets.get('NASDAQ', 0):+.1f}%")
        console.print(f"🇰🇷 한국: KOSPI {report.macro.kr_markets.get('KOSPI', 0):+.1f}%, "
                     f"KOSDAQ {report.macro.kr_markets.get('KOSDAQ', 0):+.1f}%")
        console.print(f"📉 VIX: {report.macro.vix:.1f}")
        console.print(f"😨 Fear & Greed: {report.macro.fear_greed}")
        console.print("")
        
        console.print(Panel("🔥 오늘의 핵심 인사이트", style="bold green"))
        for insight in report.insights:
            console.print(f"  • {insight}")
        console.print("")
        
        # 파일 저장
        if save:
            output_path = save_report(report)
            console.print(f"✅ 저장: {output_path}", style="bold green")
        
    except FileNotFoundError as e:
        console.print(f"❌ 에러: {e}", style="bold red")
        console.print(f"💡 먼저 실행하세요: uv run jarvis telegram fetch {date}", style="yellow")
        raise typer.Exit(1)
```

- [ ] **Step 4: Pipeline 통합 테스트 작성**

`tests/pipelines/daily_report/test_pipeline.py` 생성:

```python
"""Pipeline 통합 테스트."""
import pytest
from src.pipelines.daily_report.pipeline import run_daily_report


@pytest.mark.integration
def test_run_daily_report_with_real_data():
    """실제 2026-04-14 데이터로 전체 파이프라인 테스트."""
    report = run_daily_report("2026-04-14")
    
    # 리포트 생성 확인
    assert report.date == "2026-04-14"
    
    # 매크로 데이터 확인
    assert report.macro.vix > 0
    assert 0 <= report.macro.fear_greed <= 100
    
    # 인사이트 확인
    assert len(report.insights) >= 3
    for insight in report.insights:
        assert len(insight) > 10
    
    # NewsItem 확인
    assert len(report.news_items) > 0
    for item in report.news_items:
        assert item.theme
        assert item.emoji
        assert item.summary
        assert item.impact
```

- [ ] **Step 5: Pipeline 통합 테스트 실행**

```bash
uv run pytest tests/pipelines/daily_report/test_pipeline.py -v -m integration
```

예상 결과: End-to-end 통합 테스트 통과 (수 분 소요)

- [ ] **Step 6: CLI 테스트**

```bash
uv run jarvis report --date 2026-04-14
```

예상 결과:
- 각 stage 진행 상황 출력
- 매크로 스냅샷 출력
- 인사이트 출력
- `reports/2026-04/2026-04-14_daily_report.md` 저장

- [ ] **Step 7: Pipeline 및 CLI 커밋**

```bash
git add src/pipelines/daily_report/pipeline.py src/pipelines/daily_report/__init__.py src/cli/main.py tests/pipelines/daily_report/test_pipeline.py
git commit -m "feat(daily_report): 파이프라인 통합 및 CLI 추가

- pipeline.py: 5개 stage 오케스트레이션
- CLI: jarvis report [--date YYYY-MM-DD]
- 진행 상황 출력, 매크로/인사이트 요약
- 자동 저장: reports/YYYY-MM/YYYY-MM-DD_daily_report.md
- 테스트: end-to-end 통합 테스트"
```

---

## Task 10: 프롬프트 튜닝 도구

**파일:**
- 생성: `scripts/tune_prompts.py`
- 생성: `tests/pipelines/daily_report/evaluate_quality.py`

- [ ] **Step 1: 품질 평가 스크립트 작성**

`tests/pipelines/daily_report/evaluate_quality.py` 생성:

```python
"""Daily report 출력 품질 평가 스크립트."""
import json
import sys
from pathlib import Path
from typing import Dict, Any
from src.pipelines.daily_report.models import MappedIssue, NewsItem


def evaluate_map_output(date: str) -> Dict[str, Any]:
    """Map stage 출력 품질 평가."""
    input_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/map_{date}.json"
    
    with open(input_file, "r") as f:
        issues = [MappedIssue(**issue) for issue in json.load(f)]
    
    if not issues:
        return {"error": "No issues"}
    
    # 메트릭 계산
    avg_sources = sum(len(issue.source_ids) for issue in issues) / len(issues)
    total_themes = sum(len(issue.themes) for issue in issues)
    unique_themes = len(set(theme for issue in issues for theme in issue.themes))
    
    # 키워드 정확도 (수동 검토 필요 - 여기서는 존재 여부만)
    has_keywords = sum(1 for issue in issues if issue.keywords)
    keyword_coverage = has_keywords / len(issues)
    
    return {
        "total_issues": len(issues),
        "avg_sources_per_issue": round(avg_sources, 1),
        "total_themes": total_themes,
        "unique_themes": unique_themes,
        "keyword_coverage": round(keyword_coverage, 2),
        "clustering_quality": "GOOD" if avg_sources >= 5 else "FAIR" if avg_sources >= 3 else "POOR",
        "theme_diversity": "GOOD" if 5 <= unique_themes <= 30 else "FAIR",
    }


def evaluate_shuffle_output(date: str) -> Dict[str, Any]:
    """Shuffle stage 출력 품질 평가."""
    input_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/shuffle_{date}.json"
    
    with open(input_file, "r") as f:
        data = json.load(f)
    
    canonical_themes = data["canonical_themes"]
    original_count = sum(len(v) for v in canonical_themes.values())
    canonical_count = len(canonical_themes)
    
    normalization_rate = canonical_count / original_count if original_count > 0 else 0
    
    return {
        "original_themes": original_count,
        "canonical_themes": canonical_count,
        "normalization_rate": round(normalization_rate, 2),
        "quality": "GOOD" if 0.3 <= normalization_rate <= 0.7 else "FAIR" if 0.2 <= normalization_rate <= 0.8 else "POOR",
    }


def evaluate_reduce_output(date: str) -> Dict[str, Any]:
    """Reduce stage 출력 품질 평가."""
    input_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/reduce_{date}.json"
    
    with open(input_file, "r") as f:
        news_items = [NewsItem(**item) for item in json.load(f)]
    
    if not news_items:
        return {"error": "No news items"}
    
    # 메트릭 계산
    with_impact = sum(1 for item in news_items if item.impact)
    with_emoji = sum(1 for item in news_items if item.emoji and item.emoji in "🚀📈⚠️ℹ️📉⚡")
    with_stocks = sum(1 for item in news_items if item.stocks)
    
    return {
        "total_items": len(news_items),
        "impact_coverage": round(with_impact / len(news_items), 2),
        "emoji_coverage": round(with_emoji / len(news_items), 2),
        "stocks_coverage": round(with_stocks / len(news_items), 2),
        "quality": "GOOD" if with_impact == len(news_items) and with_emoji == len(news_items) else "FAIR",
    }


def main():
    """메인 평가 함수."""
    if len(sys.argv) < 2:
        print("사용법: python evaluate_quality.py <date>")
        print("예: python evaluate_quality.py 2026-04-14")
        sys.exit(1)
    
    date = sys.argv[1]
    
    print(f"📊 품질 평가: {date}\n")
    
    # Map 평가
    print("## Map Stage")
    map_metrics = evaluate_map_output(date)
    for key, value in map_metrics.items():
        print(f"  {key}: {value}")
    print("")
    
    # Shuffle 평가
    print("## Shuffle Stage")
    shuffle_metrics = evaluate_shuffle_output(date)
    for key, value in shuffle_metrics.items():
        print(f"  {key}: {value}")
    print("")
    
    # Reduce 평가
    print("## Reduce Stage")
    reduce_metrics = evaluate_reduce_output(date)
    for key, value in reduce_metrics.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 대화형 프롬프트 튜닝 도구 작성**

`scripts/tune_prompts.py` 생성:

```python
#!/usr/bin/env python
"""대화형 프롬프트 튜닝 도구."""
import json
import sys
from pathlib import Path


def main():
    """대화형 프롬프트 튜닝."""
    print("🔧 Daily Report 프롬프트 튜닝 도구")
    print("=" * 60)
    print("")
    print("워크플로우:")
    print("1. Stage 선택 (map, shuffle, reduce, wrapup)")
    print("2. 특정 날짜로 Stage 실행")
    print("3. 출력 검토")
    print("4. prompts.py 수정")
    print("5. 재실행 및 비교")
    print("")
    
    # Stage 선택
    print("Stage 선택:")
    print("  1. Map (이슈 추출)")
    print("  2. Shuffle (테마 정규화)")
    print("  3. Reduce (테마별 분석)")
    print("  4. Wrapup (크로스 테마 인사이트)")
    
    choice = input("\n선택 (1-4): ").strip()
    
    stage_map = {
        "1": "map",
        "2": "shuffle",
        "3": "reduce",
        "4": "wrapup",
    }
    
    if choice not in stage_map:
        print("❌ 잘못된 선택")
        sys.exit(1)
    
    stage = stage_map[choice]
    
    # 날짜 입력
    date = input("날짜 (YYYY-MM-DD, 기본값: 2026-04-14): ").strip()
    if not date:
        date = "2026-04-14"
    
    # Stage 실행
    print(f"\n⏳ {stage.capitalize()} stage 실행 중...")
    import subprocess
    
    cmd = ["python", "-m", f"src.pipelines.daily_report.stages.{stage}_stage", date]
    result = subprocess.run(cmd, capture_output=False)
    
    if result.returncode != 0:
        print(f"❌ {stage.capitalize()} stage 실행 실패")
        sys.exit(1)
    
    # 출력 파일 경로
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/{stage}_{date}.json"
    
    print(f"\n✅ 출력 저장: {output_file}")
    print("")
    print("다음 단계:")
    print(f"1. {output_file} 파일 검토")
    print(f"2. src/pipelines/daily_report/prompts.py에서 {stage.upper()}_PROMPT 수정")
    print(f"3. 이 스크립트 재실행하여 개선 확인")
    print(f"4. 품질 평가: python tests/pipelines/daily_report/evaluate_quality.py {date}")
    print("")
    print("프롬프트 버전 관리:")
    print("- 현재 프롬프트를 V1에서 V2로 복사")
    print("- V2 수정 후 PROMPT = PROMPT_V2로 변경")
    print("- 커밋 메시지에 평가 결과 포함")


if __name__ == "__main__":
    main()
```

실행 권한 부여:

```bash
chmod +x scripts/tune_prompts.py
```

- [ ] **Step 3: 튜닝 도구 사용 예시 테스트**

```bash
python scripts/tune_prompts.py
```

대화형으로:
1. Stage 선택 (예: 1 for Map)
2. 날짜 입력 (2026-04-14)
3. 출력 검토
4. prompts.py 수정
5. 재실행

- [ ] **Step 4: 품질 평가 스크립트 테스트**

```bash
python tests/pipelines/daily_report/evaluate_quality.py 2026-04-14
```

예상 결과:
- Map/Shuffle/Reduce 각 stage 메트릭 출력
- 품질 등급 (GOOD/FAIR/POOR)

- [ ] **Step 5: 튜닝 도구 커밋**

```bash
git add scripts/tune_prompts.py tests/pipelines/daily_report/evaluate_quality.py
git commit -m "feat(daily_report): 프롬프트 튜닝 도구 추가

scripts/tune_prompts.py:
- 대화형 프롬프트 튜닝 워크플로우
- Stage별 독립 실행 및 출력 검토
- 프롬프트 수정 → 재실행 → 비교

tests/.../evaluate_quality.py:
- Map/Shuffle/Reduce 품질 메트릭 계산
- 클러스터링 품질, 정규화 비율, 이모지 커버리지
- GOOD/FAIR/POOR 등급

사용법:
  python scripts/tune_prompts.py
  python tests/pipelines/daily_report/evaluate_quality.py 2026-04-14"
```

---

## 마무리 및 문서 업데이트

- [ ] **Step 1: 전체 테스트 실행**

```bash
uv run pytest tests/pipelines/daily_report/ -v
```

예상 결과: 모든 테스트 통과

- [ ] **Step 2: 실제 리포트 생성 테스트**

```bash
uv run jarvis report --date 2026-04-14
```

예상 결과:
- 모든 stage 성공적으로 실행
- `reports/2026-04/2026-04-14_daily_report.md` 생성
- 수동으로 리포트 품질 검토

- [ ] **Step 3: README.md 업데이트**

Features 섹션에 추가:
```markdown
### Daily Report Pipeline

텔레그램 채널 메시지 기반 일일 시장 리포트 자동 생성.

- **테마 기반 클러스터링**: 의미론적 테마로 메시지 그룹핑
- **LLM 파이프라인**: gpt-4o (일관성) + gpt-5.2 (분석)
- **한글 출력**: 이모지, bullet points, Impact 문구
- **자동 뉴스 검색**: DuckDuckGo Search 통합
```

Commands 섹션에 추가:
```markdown
#### jarvis report

일일 시장 리포트 생성 (텔레그램 메시지 분석).

```bash
# 어제 날짜로 리포트 생성
uv run jarvis report

# 특정 날짜 리포트
uv run jarvis report --date 2026-04-14
```

출력: `reports/YYYY-MM/YYYY-MM-DD_daily_report.md`
```

- [ ] **Step 4: docs/CLI_USAGE.md 업데이트**

"7. telegram" 섹션 다음에 "8. report" 섹션 추가:

```markdown
### 8. report - 일일 시장 리포트

**특징:**
- 텔레그램 메시지 분석
- 테마 기반 클러스터링
- 한글 리포트 (이모지, Impact)
- 매크로 지표 포함

**요구사항:**
- 텔레그램 데이터 수집 완료 (jarvis telegram fetch)
- OPENAI_API_KEY 필요

**사용법:**
```bash
uv run jarvis report [OPTIONS]
```

**옵션:**
- `--date`: 날짜 (YYYY-MM-DD), 기본값: 어제
- `--save/--no-save`: 파일 저장 여부 (기본값: True)

**예시:**
```bash
# 어제 리포트
uv run jarvis report

# 특정 날짜
uv run jarvis report --date 2026-04-14

# 저장 안 함
uv run jarvis report --no-save
```

**출력 내용:**
- **매크로 스냅샷**: 미국/한국 시장, VIX, Fear & Greed, 환율
- **핵심 인사이트**: 크로스 테마 연결
- **테마별 분석**: 이슈, 뉴스, Impact, 관련 종목
```

- [ ] **Step 5: CLAUDE.md 업데이트**

Architecture 섹션에 추가:

```markdown
| Layer | Location | Role |
|-------|----------|------|
| **Pipelines** | `src/pipelines/` | 워크플로우 (daily_report: 텔레그램 분석) |
```

Common Commands 섹션에 추가:

```bash
uv run jarvis report            # 일일 시장 리포트 (텔레그램 분석)
```

- [ ] **Step 6: 디자인 스펙 문서 생성**

`docs/superpowers/specs/2026-04-15-daily-report-design.md` 작성 (이전 세션에서 작성한 내용):
- 개요, 아키텍처, 모델, 프롬프트 전략
- V1 vs V2 비교
- Screen data 통합 계획

- [ ] **Step 7: 최종 커밋**

```bash
git add README.md docs/CLI_USAGE.md CLAUDE.md docs/superpowers/specs/2026-04-15-daily-report-design.md
git commit -m "docs: daily_report 파이프라인 문서 추가

- README.md: Features 및 Commands 섹션 업데이트
- docs/CLI_USAGE.md: report 명령어 상세 가이드
- CLAUDE.md: Architecture 및 Common Commands 업데이트
- docs/superpowers/specs/: daily_report 설계 명세서

구현 완료:
- 4-stage 파이프라인 (Ingest-Map-Shuffle-Reduce-Wrapup)
- 테마 기반 클러스터링
- gpt-4o + gpt-5.2 + ddgs
- 프롬프트 버전 관리 및 튜닝 도구"
```

---

## 프롬프트 개선 권장 사항

### Map Stage 개선 전략

**현재 문제 징후:**
- 클러스터링 비율 < 3 (이슈당 평균 소스 수)
- 테마가 섹터 태그처럼 보임 ("반도체", "자동차")

**개선 방법:**
1. Few-shot 예시 추가 (Bloom Energy 이외)
2. 프롬프트에 "섹터가 아닌 의미론적 주제" 강조
3. Temperature 조정 (0.3 → 0.4로 실험)

**평가:**
```bash
python tests/pipelines/daily_report/evaluate_quality.py 2026-04-14
```

### Shuffle Stage 개선 전략

**현재 문제 징후:**
- 정규화 비율 > 0.8 (거의 안 뭉갬)
- 정규화 비율 < 0.2 (너무 뭉갬)

**개선 방법:**
1. Few-shot 예시에서 적절한 그룹핑 보여주기
2. Temperature 조정 (0.1 유지 또는 0.05로 낮춤)
3. 프롬프트에 "광범위하게 묶지 말 것" 재강조

### Reduce Stage 개선 전략

**현재 문제 징후:**
- Impact 문구 누락
- 이모지 부적절
- Bullet point 형식 안 지킴

**개선 방법:**
1. V1 리포트 스타일 Few-shot 예시 추가
2. 출력 형식 JSON schema를 더 명확히
3. Temperature 조정 (0.5 → 0.6으로 실험)

### Wrapup Stage 개선 전략

**현재 문제 징후:**
- 단순 요약 (NewsItem rehash)
- 크로스 테마 연결 부족

**개선 방법:**
1. "단순 요약 금지" 강조
2. "테마 간 연결" 예시 추가
3. Temperature 유지 (0.7)

---

## 프롬프트 튜닝 반복 체크리스트

매 반복마다 확인:

- [ ] Stage 독립 실행 (CLI)
- [ ] 출력 JSON 수동 검토
- [ ] evaluate_quality.py로 메트릭 확인
- [ ] 실패 패턴 식별
- [ ] prompts.py에서 V2 작성
- [ ] PROMPT = PROMPT_V2로 변경
- [ ] 재실행 및 비교
- [ ] 개선 확인 시 커밋

**커밋 메시지 포맷:**
```
prompt: [Stage] [변경 내용] (v1→v2)

변경사항: [구체적 변경]
결과: [메트릭 개선 내용]

Before: [이전 메트릭]
After: [이후 메트릭]
```

**예:**
```
prompt: Map 클러스터링 개선 (v1→v2)

변경사항: 
- Bloom Energy + HBM 예시 추가
- "섹터 태그 금지" 문구 강조

결과:
- 클러스터링 비율: 3.2 → 7.1
- 테마 구체성: "반도체" → "AI 메모리 업사이클" 비율 80%

Before: avg_sources=3.2, unique_themes=42
After: avg_sources=7.1, unique_themes=28
```
