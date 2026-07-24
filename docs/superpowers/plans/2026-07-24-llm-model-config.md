# LLM 모델 설정 일원화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** daily(`report daily`), daily_v2(`report daily-v2`), analyze, brief 파이프라인의 LLM provider/model/temperature를 config.yaml `llm:` 섹션 단일 소스로 일원화한다.

**Architecture:** `src/core/config.py`의 Pydantic `AppConfig`에 `llm` 섹션을 추가하고, `resolve(pipeline, stage)`로 defaults 병합된 완성형 설정을 얻는다. 공용 `StageLLMConfig`(create_llm + build_messages)를 `src/llm/stage_config.py`로 통합하고, 각 파이프라인은 `resolve_stage_llm()`으로 이를 얻는다. CLI `--provider` 플래그와 `STOCK_REPORT_*` env 체인은 삭제한다.

**Tech Stack:** Python 3.13, Pydantic v2, LangChain, Typer, pytest, uv

**Spec:** `docs/superpowers/specs/2026-07-24-llm-model-config-design.md`

## Global Constraints

- 패키지 관리는 항상 `uv` (`uv run pytest`), pip 직접 사용 금지.
- 모델은 GPT-5.6 패밀리만: 디폴트 `gpt-5.6-terra`, 고볼륨 스테이지(map/shuffle/extraction) `gpt-5.6-luna`, daily_v2 synthesis `gpt-5.6-sol`.
- config 키는 CLI 명령 기준: `daily`(map/shuffle/reduce/wrapup), `daily_v2`(extraction/synthesis), `analyze`, `brief`.
- config.yaml에 `llm:` 섹션이 없어도 코드 기본값(위 배정과 동일)으로 동작해야 한다.
- 잘못된 설정은 조용히 폴백하지 말고 ValidationError/KeyError로 즉시 실패.
- API 키·Bedrock 엔드포인트는 `.env` 유지 — provider/model/temperature만 config.yaml로 이동.
- 커밋 메시지 끝에 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` 추가.

---

### Task 1: core config — LLM 설정 모델과 resolve

**Files:**
- Modify: `src/core/config.py`
- Test: `tests/core/test_config.py`

**Interfaces:**
- Produces: `LLMEntryConfig`, `LLMDefaultsConfig`, `ResolvedLLMEntry`, `LLMConfig.resolve(pipeline: str, stage: str | None) -> ResolvedLLMEntry`, `AppConfig.llm: LLMConfig`, `get_app_config() -> AppConfig` (lru_cache).

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/core/test_config.py`에 추가:

```python
import pytest

from src.core.config import AppConfig, LLMConfig, get_app_config, load_config


def test_llm_defaults_when_section_absent():
    config = AppConfig()
    resolved = config.llm.resolve("analyze")
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-5.6-terra"
    assert resolved.temperature == 0.0


def test_llm_daily_stage_code_defaults():
    llm = LLMConfig()
    assert llm.resolve("daily", "map").model == "gpt-5.6-luna"
    assert llm.resolve("daily", "map").temperature == 0.2
    assert llm.resolve("daily", "shuffle").model == "gpt-5.6-luna"
    assert llm.resolve("daily", "shuffle").temperature == 0.1
    assert llm.resolve("daily", "reduce").model == "gpt-5.6-terra"
    assert llm.resolve("daily", "reduce").temperature == 0.3
    assert llm.resolve("daily", "wrapup").temperature == 0.4


def test_llm_daily_v2_stage_code_defaults():
    llm = LLMConfig()
    extraction = llm.resolve("daily_v2", "extraction")
    synthesis = llm.resolve("daily_v2", "synthesis")
    assert extraction.model == "gpt-5.6-luna"
    assert extraction.temperature == 0.1
    assert synthesis.model == "gpt-5.6-sol"
    assert synthesis.temperature == 0.1


def test_llm_stage_entry_inherits_unset_fields_from_defaults():
    llm = LLMConfig.model_validate(
        {
            "defaults": {"provider": "openai", "model": "gpt-5.6-terra", "temperature": 0.0},
            "daily": {"reduce": {"temperature": 0.9}},
        }
    )
    resolved = llm.resolve("daily", "reduce")
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-5.6-terra"  # defaults 상속
    assert resolved.temperature == 0.9  # 명시 필드만 오버라이드


def test_llm_resolve_unknown_pipeline_raises():
    with pytest.raises(KeyError):
        LLMConfig().resolve("quick_check")


def test_llm_resolve_unknown_stage_raises():
    with pytest.raises(KeyError):
        LLMConfig().resolve("daily", "nonexistent")


def test_llm_resolve_staged_pipeline_requires_stage():
    with pytest.raises(KeyError):
        LLMConfig().resolve("daily")


def test_llm_unknown_stage_key_in_yaml_fails_validation():
    with pytest.raises(ValueError):
        LLMConfig.model_validate({"daily": {"tpyo": {"temperature": 0.5}}})


def test_get_app_config_is_cached():
    get_app_config.cache_clear()
    assert get_app_config() is get_app_config()
    get_app_config.cache_clear()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/core/test_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'LLMConfig'`

- [ ] **Step 3: 구현** — `src/core/config.py`를 다음으로 교체 (기존 CacheConfig/TechnicalConfig/load_config 유지):

```python
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class CacheConfig(BaseModel):
    quote_ttl: int = 60
    history_ttl: int = 300
    indicators_ttl: int = 300


class TechnicalConfig(BaseModel):
    strategies: list[str] = ["trend"]


class LLMEntryConfig(BaseModel):
    """파이프라인/스테이지별 부분 오버라이드 — 명시한 필드만 defaults를 덮는다."""

    provider: str | None = None
    model: str | None = None
    temperature: float | None = None


class LLMDefaultsConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-5.6-terra"
    temperature: float = 0.0


class ResolvedLLMEntry(BaseModel):
    provider: str
    model: str
    temperature: float


_PIPELINE_STAGES: dict[str, tuple[str, ...]] = {
    "daily": ("map", "shuffle", "reduce", "wrapup"),
    "daily_v2": ("extraction", "synthesis"),
}
_SINGLE_ENTRY_PIPELINES = ("analyze", "brief")


def _default_daily() -> dict[str, LLMEntryConfig]:
    return {
        "map": LLMEntryConfig(model="gpt-5.6-luna", temperature=0.2),
        "shuffle": LLMEntryConfig(model="gpt-5.6-luna", temperature=0.1),
        "reduce": LLMEntryConfig(temperature=0.3),
        "wrapup": LLMEntryConfig(temperature=0.4),
    }


def _default_daily_v2() -> dict[str, LLMEntryConfig]:
    return {
        "extraction": LLMEntryConfig(model="gpt-5.6-luna", temperature=0.1),
        "synthesis": LLMEntryConfig(model="gpt-5.6-sol", temperature=0.1),
    }


class LLMConfig(BaseModel):
    defaults: LLMDefaultsConfig = LLMDefaultsConfig()
    daily: dict[str, LLMEntryConfig] = Field(default_factory=_default_daily)
    daily_v2: dict[str, LLMEntryConfig] = Field(default_factory=_default_daily_v2)
    analyze: LLMEntryConfig = LLMEntryConfig()
    brief: LLMEntryConfig = LLMEntryConfig()

    @model_validator(mode="after")
    def _reject_unknown_stage_keys(self) -> "LLMConfig":
        for pipeline, stages in _PIPELINE_STAGES.items():
            unknown = set(getattr(self, pipeline)) - set(stages)
            if unknown:
                raise ValueError(f"llm.{pipeline}에 알 수 없는 스테이지: {sorted(unknown)}")
        return self

    def resolve(self, pipeline: str, stage: str | None = None) -> ResolvedLLMEntry:
        """defaults와 병합된 완성형 LLM 설정을 반환한다. 잘못된 키는 즉시 실패."""
        if pipeline in _PIPELINE_STAGES:
            if stage is None or stage not in _PIPELINE_STAGES[pipeline]:
                raise KeyError(f"llm.{pipeline}의 stage가 잘못됨: {stage!r}")
            entry = getattr(self, pipeline).get(stage, LLMEntryConfig())
        elif pipeline in _SINGLE_ENTRY_PIPELINES:
            if stage is not None:
                raise KeyError(f"llm.{pipeline}은 stage를 받지 않음: {stage!r}")
            entry = getattr(self, pipeline)
        else:
            raise KeyError(f"알 수 없는 llm pipeline: {pipeline!r}")
        defaults = self.defaults
        return ResolvedLLMEntry(
            provider=entry.provider or defaults.provider,
            model=entry.model or defaults.model,
            temperature=(
                entry.temperature if entry.temperature is not None else defaults.temperature
            ),
        )


class AppConfig(BaseModel):
    technical: TechnicalConfig = TechnicalConfig()
    cache: CacheConfig = CacheConfig()
    llm: LLMConfig = LLMConfig()


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load configuration from YAML file or use defaults."""
    if config_path is None:
        config_path = Path("config.yaml")

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return AppConfig(**data)

    return AppConfig()


@lru_cache(maxsize=1)
def get_app_config() -> AppConfig:
    """cwd의 config.yaml을 1회 로드해 캐시한다. 테스트에서는 cache_clear() 사용."""
    return load_config()
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/core/test_config.py -v`
Expected: PASS (기존 테스트 포함 전부)

- [ ] **Step 5: Commit**

```bash
git add src/core/config.py tests/core/test_config.py
git commit -m "feat: add llm section to AppConfig with per-stage resolve"
```

---

### Task 2: 공용 StageLLMConfig — src/llm/stage_config.py

**Files:**
- Create: `src/llm/stage_config.py`
- Test: `tests/llm/test_stage_config.py`

**Interfaces:**
- Consumes: `get_app_config()` (Task 1)
- Produces: `StageLLMConfig(provider, model, temperature)` frozen dataclass — `.create_llm() -> BaseChatModel`, `.build_messages(system_prompt, user_prompt) -> list[BaseMessage]`; `resolve_stage_llm(pipeline: str, stage: str | None = None) -> StageLLMConfig`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/llm/test_stage_config.py` 생성:

```python
from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.stage_config import StageLLMConfig, resolve_stage_llm


def test_build_messages_plain_for_openai():
    config = StageLLMConfig(provider="openai", model="gpt-5.6-terra", temperature=0.0)
    messages = config.build_messages("sys", "user")
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert messages[0].additional_kwargs == {}


def test_build_messages_adds_cache_control_for_anthropic():
    config = StageLLMConfig(provider="anthropic", model="claude-x", temperature=0.0)
    messages = config.build_messages("sys", "user")
    assert messages[0].additional_kwargs == {"cache_control": {"type": "ephemeral"}}


def test_resolve_stage_llm_returns_config_backed_values():
    resolved = resolve_stage_llm("daily_v2", "synthesis")
    assert isinstance(resolved, StageLLMConfig)
    assert resolved.model == "gpt-5.6-sol"
    assert resolved.temperature == 0.1
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/llm/test_stage_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.llm.stage_config'`

- [ ] **Step 3: 구현** — `src/llm/stage_config.py` 생성 (daily_report/config.py의 StageLLMConfig를 그대로 이동 + resolve_stage_llm 추가):

```python
"""파이프라인 스테이지 공용 LLM 설정 — config.yaml llm 섹션이 단일 소스."""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.core.config import get_app_config
from src.llm.provider import LLMProvider


@dataclass(frozen=True)
class StageLLMConfig:
    """스테이지별 LLM 설정."""

    provider: str
    model: str
    temperature: float

    def create_llm(self) -> BaseChatModel:
        return LLMProvider.create(
            provider=self.provider,
            model=self.model,
            temperature=self.temperature,
        )

    def build_messages(self, system_prompt: str, user_prompt: str) -> list[BaseMessage]:
        """LLM 메시지 리스트 생성. Anthropic이면 system prompt 캐싱 적용."""
        kwargs = {}
        if self.provider == "anthropic":
            kwargs["cache_control"] = {"type": "ephemeral"}
        return [
            SystemMessage(content=system_prompt, additional_kwargs=kwargs),
            HumanMessage(content=user_prompt),
        ]


def resolve_stage_llm(pipeline: str, stage: str | None = None) -> StageLLMConfig:
    """config.yaml llm 섹션에서 defaults 병합된 스테이지 설정을 얻는다."""
    entry = get_app_config().llm.resolve(pipeline, stage)
    return StageLLMConfig(
        provider=entry.provider,
        model=entry.model,
        temperature=entry.temperature,
    )
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/llm/test_stage_config.py -v`
Expected: PASS
주의: `test_resolve_stage_llm_returns_config_backed_values`는 repo 루트 config.yaml의 llm 섹션(Task 3 이전엔 코드 기본값)을 읽는다 — 둘 다 sol/0.1이므로 Task 3 전후 모두 통과해야 한다.

- [ ] **Step 5: Commit**

```bash
git add src/llm/stage_config.py tests/llm/test_stage_config.py
git commit -m "feat: add shared StageLLMConfig with config-backed resolve_stage_llm"
```

---

### Task 3: config.yaml llm 섹션 추가

**Files:**
- Modify: `config.yaml` (repo 루트)
- Test: `tests/core/test_config.py` (골든 정합성 1건 추가)

**Interfaces:**
- Consumes: Task 1의 스키마
- Produces: repo config.yaml의 `llm:` 섹션 (운영 기본값)

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/core/test_config.py`에 추가 (repo config.yaml이 스키마에 유효하고 명시 섹션을 갖는지 고정):

```python
from pathlib import Path


def test_repo_config_yaml_llm_section_matches_code_defaults():
    repo_config = Path(__file__).resolve().parents[2] / "config.yaml"
    config = load_config(repo_config)
    assert config.llm.model_dump() == LLMConfig().model_dump()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/core/test_config.py::test_repo_config_yaml_llm_section_matches_code_defaults -v`
Expected: PASS가 나올 수 있음(섹션 부재 → 코드 기본값). 섹션을 **명시적으로** 추가한 뒤에도 동일해야 한다는 골든 테스트이므로, 먼저 PASS라면 그대로 진행.

- [ ] **Step 3: config.yaml 끝에 llm 섹션 추가**

```yaml
llm:
  defaults:
    provider: openai
    model: gpt-5.6-terra
    temperature: 0.0
  daily:                 # jarvis report daily
    map:     { model: gpt-5.6-luna, temperature: 0.2 }
    shuffle: { model: gpt-5.6-luna, temperature: 0.1 }
    reduce:  { temperature: 0.3 }
    wrapup:  { temperature: 0.4 }
  daily_v2:              # jarvis report daily-v2
    extraction: { model: gpt-5.6-luna, temperature: 0.1 }
    synthesis:  { model: gpt-5.6-sol,  temperature: 0.1 }
  analyze: {}            # jarvis analyze → defaults(terra)
  brief:   {}            # jarvis brief → defaults(terra)
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/core/ -v`
Expected: PASS — yaml 명시값과 코드 기본값이 완전히 일치

- [ ] **Step 5: Commit**

```bash
git add config.yaml tests/core/test_config.py
git commit -m "feat: add llm model config section to config.yaml"
```

---

### Task 4: daily_report 마이그레이션

**Files:**
- Modify: `src/pipelines/daily_report/config.py`
- Modify: `src/pipelines/daily_report/stages/map_stage.py`, `shuffle_stage.py`, `reduce_stage.py`, `wrapup_stage.py`
- Test: `tests/core/test_config.py` (Task 1에서 커버) + 기존 daily_report 테스트 회귀

**Interfaces:**
- Consumes: `resolve_stage_llm("daily", stage)` (Task 2)
- Produces: `src/pipelines/daily_report/config.py`의 `get_stage_llm(stage: str) -> StageLLMConfig`

- [ ] **Step 1: config.py 교체** — `src/pipelines/daily_report/config.py`에서 `StageLLMConfig` 클래스 정의와 `MAP_LLM`/`SHUFFLE_LLM`/`REDUCE_LLM`/`WRAPUP_LLM` 상수, langchain/LLMProvider import를 삭제하고 아래로 대체 (`MAP_MAX_TOKENS_PER_CHUNK`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `MACRO_MAX_RETRIES`는 유지):

```python
"""Daily report 파이프라인 설정."""

from src.llm.stage_config import StageLLMConfig, resolve_stage_llm


def get_stage_llm(stage: str) -> StageLLMConfig:
    """config.yaml llm.daily 섹션에서 스테이지 설정을 얻는다."""
    return resolve_stage_llm("daily", stage)


__all__ = ["StageLLMConfig", "get_stage_llm"]

# Map stage 청크 설정
MAP_MAX_TOKENS_PER_CHUNK = 80_000

# LLM 호출 재시도/타임아웃
LLM_TIMEOUT_SECONDS = 180.0
LLM_MAX_RETRIES = 3

# 매크로 데이터 수집 재시도
MACRO_MAX_RETRIES = 3
```

- [ ] **Step 2: 4개 스테이지 파일 수정** — 각 파일에서 import와 사용부를 교체:

`map_stage.py`:
- `from src.pipelines.daily_report.config import MAP_LLM, MAP_MAX_TOKENS_PER_CHUNK` → `from src.pipelines.daily_report.config import MAP_MAX_TOKENS_PER_CHUNK, get_stage_llm`
- `llm = MAP_LLM.create_llm()` → `llm = get_stage_llm("map").create_llm()`
- `messages = MAP_LLM.build_messages(system_prompt, user_prompt)` → `messages = get_stage_llm("map").build_messages(system_prompt, user_prompt)`

`shuffle_stage.py`:
- `from src.pipelines.daily_report.config import SHUFFLE_LLM` → `from src.pipelines.daily_report.config import get_stage_llm`
- `SHUFFLE_LLM.create_llm()` → `get_stage_llm("shuffle").create_llm()`
- `SHUFFLE_LLM.build_messages(...)` → `get_stage_llm("shuffle").build_messages(...)`

`reduce_stage.py`:
- `from src.pipelines.daily_report.config import REDUCE_LLM` → `from src.pipelines.daily_report.config import get_stage_llm`
- `REDUCE_LLM.create_llm()` → `get_stage_llm("reduce").create_llm()`
- `REDUCE_LLM.build_messages(...)` → `get_stage_llm("reduce").build_messages(...)`

`wrapup_stage.py`:
- `from src.pipelines.daily_report.config import WRAPUP_LLM` → `from src.pipelines.daily_report.config import get_stage_llm`
- `WRAPUP_LLM.create_llm()` → `get_stage_llm("wrapup").create_llm()`
- `WRAPUP_LLM.build_messages(...)` → `get_stage_llm("wrapup").build_messages(...)`

- [ ] **Step 3: 잔여 참조 확인**

Run: `grep -rn "MAP_LLM\|SHUFFLE_LLM\|REDUCE_LLM\|WRAPUP_LLM" src/ tests/ --include="*.py"`
Expected: 출력 없음

- [ ] **Step 4: 회귀 테스트**

Run: `uv run pytest tests/pipelines/daily_report/ tests/llm/ tests/core/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipelines/daily_report/
git commit -m "refactor: daily_report stages read LLM config from config.yaml"
```

---

### Task 5: stock_report config 재작성 + classify.py 주입 전환

**Files:**
- Modify: `src/pipelines/stock_report/config.py`
- Modify: `src/pipelines/stock_report/classify.py:1139-1330`
- Test: `tests/pipelines/stock_report/test_config.py` (재작성)

**Interfaces:**
- Consumes: `StageLLMConfig`, `resolve_stage_llm` (Task 2)
- Produces: `get_semantic_extraction_llm_config() -> StageLLMConfig` (인자 없음), `get_report_synthesis_llm_config() -> StageLLMConfig` (인자 없음), `classify_messages(normalized_messages, *, taxonomy, system_prompt=None, llm_config: StageLLMConfig | None = None)`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/pipelines/stock_report/test_config.py` 전체를 다음으로 교체 (env 체인 테스트 3건 삭제):

```python
from __future__ import annotations

from src.llm.stage_config import StageLLMConfig
from src.pipelines.stock_report.config import (
    get_report_synthesis_llm_config,
    get_semantic_extraction_llm_config,
)


def test_semantic_extraction_config_from_yaml_defaults() -> None:
    config = get_semantic_extraction_llm_config()
    assert isinstance(config, StageLLMConfig)
    assert config.provider == "openai"
    assert config.model == "gpt-5.6-luna"
    assert config.temperature == 0.1


def test_report_synthesis_config_from_yaml_defaults() -> None:
    config = get_report_synthesis_llm_config()
    assert config.provider == "openai"
    assert config.model == "gpt-5.6-sol"
    assert config.temperature == 0.1
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/pipelines/stock_report/test_config.py -v`
Expected: FAIL — 기존 시그니처는 provider 인자 필수

- [ ] **Step 3: config.py 재작성** — `src/pipelines/stock_report/config.py`에서 `SemanticExtractionLLMConfig` 클래스, `StockReportLLMConfig` alias, `os` import, env 체인을 삭제하고 getter를 교체 (`SEMANTIC_EXTRACTION_*` 상수, `GOOGLE_GROUNDING_DEFAULT_MODEL`, `GoogleGroundingConfig`, `get_google_grounding_config`는 그대로 유지 — grounding은 범위 밖):

```python
from __future__ import annotations

import os
from dataclasses import dataclass

from src.llm.stage_config import StageLLMConfig, resolve_stage_llm


def get_semantic_extraction_llm_config() -> StageLLMConfig:
    """daily_v2 extraction 스테이지 LLM 설정 (config.yaml llm.daily_v2.extraction)."""
    return resolve_stage_llm("daily_v2", "extraction")


def get_report_synthesis_llm_config() -> StageLLMConfig:
    """daily_v2 synthesis 스테이지 LLM 설정 (config.yaml llm.daily_v2.synthesis)."""
    return resolve_stage_llm("daily_v2", "synthesis")


SEMANTIC_EXTRACTION_MAX_CONCURRENCY = 8
SEMANTIC_EXTRACTION_TIMEOUT_SECONDS = 180.0
SEMANTIC_EXTRACTION_MAX_RETRIES = 3

GOOGLE_GROUNDING_DEFAULT_MODEL = "gemini-3.5-flash"


@dataclass(frozen=True)
class GoogleGroundingConfig:
    api_key: str | None = None
    model: str = GOOGLE_GROUNDING_DEFAULT_MODEL


def get_google_grounding_config() -> GoogleGroundingConfig:
    return GoogleGroundingConfig(
        api_key=os.getenv("GOOGLE_API_KEY"),
        model=os.getenv("STOCK_REPORT_GOOGLE_MODEL") or GOOGLE_GROUNDING_DEFAULT_MODEL,
    )
```

- [ ] **Step 4: classify.py 주입 전환** — `provider: str` 스레딩을 `llm_config: StageLLMConfig` 주입으로 교체. 규칙: 함수 파라미터의 `provider: str,` → `llm_config: StageLLMConfig,`, 호출부의 `provider=provider,` → `llm_config=llm_config,`, 로그·태그·metadata의 `provider` 값 → `llm_config.provider`. 구체적으로:

임포트에 추가: `from src.llm.stage_config import StageLLMConfig`

`_get_llm_runtime` (line 1139-1148) 교체:

```python
@lru_cache(maxsize=4)
def _get_llm_runtime(llm_config: StageLLMConfig):
    logger.info(
        "Semantic extraction runtime initialized: provider=%s model=%s temperature=%.2f",
        llm_config.provider,
        llm_config.model,
        llm_config.temperature,
    )
    return llm_config.create_llm()
```

`_extract_message_semantics`: 파라미터 `provider: str` → `llm_config: StageLLMConfig`; 본문 첫 줄 `llm_config, llm = _get_llm_runtime(provider)` → `llm = _get_llm_runtime(llm_config)`; config dict의 `f"provider:{provider}"` → `f"provider:{llm_config.provider}"`, `"provider": provider` → `"provider": llm_config.provider`.

`_classify_single_message`, `_classify_messages_async`: 파라미터 `provider: str` → `llm_config: StageLLMConfig`; 내부 전달 `provider=provider` → `llm_config=llm_config`; 로그 포맷 인자 `provider` → `llm_config.provider`.

`classify_messages` (공개 엔트리포인트) 교체:

```python
def classify_messages(
    normalized_messages: list[NormalizedMessage],
    *,
    taxonomy: TaxonomyRegistry,
    system_prompt: str | None = None,
    llm_config: StageLLMConfig | None = None,
) -> list[ClassifiedMessage]:
    """pipeline/CLI가 사용하는 동기 엔트리포인트다.

    목적:
    - 외부 호출부는 단순하게 유지하고, 실제 분류 작업은 async 구현에 위임한다.
    - llm_config 미지정 시 config.yaml(llm.daily_v2.extraction)을 따른다.
      실험(tuning)에서는 명시 주입으로 오버라이드한다.
    """
    if not normalized_messages:
        return []
    resolved_llm_config = llm_config or get_semantic_extraction_llm_config()
    resolved_system_prompt = system_prompt or SEMANTIC_EXTRACTION_SYSTEM_PROMPT
    return asyncio.run(
        _classify_messages_async(
            normalized_messages,
            taxonomy=taxonomy,
            llm_config=resolved_llm_config,
            system_prompt=resolved_system_prompt,
        )
    )
```

- [ ] **Step 5: 확인**

Run: `uv run pytest tests/pipelines/stock_report/test_config.py -v && grep -n "provider" src/pipelines/stock_report/classify.py | grep -v "llm_config.provider" | grep -v "^.*#"`
Expected: 테스트 PASS, classify.py에 남은 `provider`는 `llm_config.provider` 파생 사용뿐

주의: 이 시점에서 `pipeline.py`/`tuning.py`/`pdf_classify.py`가 아직 옛 시그니처로 호출하므로 전체 테스트는 깨진다 — Task 6·7에서 정리한다. 이 Task의 커밋은 컴파일 가능 상태(import 오류 없음)면 된다.

- [ ] **Step 6: Commit**

```bash
git add src/pipelines/stock_report/config.py src/pipelines/stock_report/classify.py tests/pipelines/stock_report/test_config.py
git commit -m "refactor: stock_report extraction reads LLM config from config.yaml"
```

---

### Task 6: synthesize.py + pipeline.py 주입 전환

**Files:**
- Modify: `src/pipelines/stock_report/synthesize.py`
- Modify: `src/pipelines/stock_report/pipeline.py`
- Test: `tests/pipelines/stock_report/test_synthesize_t17.py` 등 기존 테스트 회귀

**Interfaces:**
- Consumes: `get_report_synthesis_llm_config()` (Task 5, 인자 없음)
- Produces: `synthesize_daily(bundle, *, search_fn=None)` — provider 파라미터 제거; `run_daily_v2(date, data_dir, config_path, taxonomy_path, preview_limit, google_grounding)` — provider 파라미터 제거

- [ ] **Step 1: synthesize.py 수정** — 규칙 동일. 구체적으로:
  - `_run_synthesis_call(system, user, schema, provider)` → `_run_synthesis_call(system, user, schema)`; 본문 `get_report_synthesis_llm_config(provider)` → `get_report_synthesis_llm_config()`; run_name/태그/metadata의 `provider` → `llm_config.provider`.
  - `synthesize_category`/`synthesize_ticker`/`synthesize_overview` 및 그 하위에서 `provider` 파라미터 제거; `get_report_synthesis_llm_config(provider)` 3개 호출부 → `get_report_synthesis_llm_config()`; `_run_synthesis_call(..., provider)` 호출부에서 인자 제거; 로그의 `provider` → `llm_config.provider` (llm_config가 없는 스코프의 로그면 `get_report_synthesis_llm_config().provider` 대신 로그 인자 자체를 제거).
  - `synthesize_daily(bundle, *, provider, search_fn=None)` → `synthesize_daily(bundle, *, search_fn=None)`.

- [ ] **Step 2: pipeline.py 수정**
  - `_stage_classify(normalized, *, taxonomy, provider)` → `_stage_classify(normalized, *, taxonomy)`; 본문 `classify_messages(normalized, taxonomy=taxonomy, provider=provider)` → `classify_messages(normalized, taxonomy=taxonomy)`.
  - `_stage_local_evidence_synthesis(bundle, *, provider, search_fn=None)` → `_stage_local_evidence_synthesis(bundle, *, search_fn=None)`; 본문 `synthesize_daily(bundle, provider=provider, search_fn=search_fn)` → `synthesize_daily(bundle, search_fn=search_fn)`.
  - `run_daily_v2(..., provider: str, ...)`에서 provider 파라미터 삭제. 본문 시작부는 이미 `semantic_llm_config = get_semantic_extraction_llm_config(provider)` / `synthesis_llm_config = get_report_synthesis_llm_config(provider)`를 갖고 있으므로 인자만 제거. 시작 로그의 `provider=%s` 인자는 `semantic_llm_config.provider`로 대체.
  - `_stage_persist_report(conn, *, report_date, provider, ...)`는 시그니처 유지, 호출부에서 `provider=synthesis_llm_config.provider` 전달 (DB 기록용 provider는 유지).
  - `DailyV2RunResult`에 provider 필드가 있으면 동일하게 `synthesis_llm_config.provider`로 채운다.

- [ ] **Step 3: 회귀 테스트 + fake 정리**

Run: `uv run pytest tests/pipelines/stock_report/ -q`
Expected: `test_synthesize_t17.py`가 `get_report_synthesis_llm_config`를 patch하므로 호출 인자 변화에 따라 fake 시그니처 수정 필요할 수 있음 — provider 인자를 받던 fake는 무인자 lambda로 수정. 최종 PASS.

- [ ] **Step 4: Commit**

```bash
git add src/pipelines/stock_report/synthesize.py src/pipelines/stock_report/pipeline.py tests/pipelines/stock_report/
git commit -m "refactor: stock_report synthesis/pipeline drop provider threading"
```

---

### Task 7: pdf_classify / pdf_ingest / tuning / 스크립트

**Files:**
- Modify: `src/pipelines/stock_report/pdf_classify.py`, `pdf_ingest.py`, `tuning.py`
- Modify: `scripts/stock_report_prompt_tuning.py`
- Test: `tests/pipelines/stock_report/test_tuning.py`

**Interfaces:**
- Consumes: `classify_messages(..., llm_config=None)` (Task 5), `get_semantic_extraction_llm_config()` (Task 5)
- Produces: `run_ingest_pdf(...)` — provider 파라미터 제거; `run_prompt_tuning_round(..., llm_config: StageLLMConfig | None = None)` — provider 파라미터 대체; `with_model_override`/`_EnvOverrideContext`/`_NoopContext` 삭제

- [ ] **Step 1: pdf_classify.py / pdf_ingest.py** — Task 5·6과 동일 규칙: `provider: str` 파라미터 제거, `get_semantic_extraction_llm_config(provider)` → `get_semantic_extraction_llm_config()`, 태그·metadata·로그의 provider는 함수 시작에서 얻은 `llm_config.provider` 사용, `provider=provider` 전달 인자 제거.

- [ ] **Step 2: tuning.py**
  - `run_prompt_tuning_round`의 `provider: str = "openai"` 파라미터를 `llm_config: StageLLMConfig | None = None`으로 교체. 본문 첫 부분: `llm_config = llm_config or get_semantic_extraction_llm_config()`. 로그와 `PromptTuningRunResult(provider=...)`는 `llm_config.provider` 사용. `classify_messages(..., provider=provider, ...)` → `classify_messages(..., llm_config=llm_config, ...)`.
  - `with_model_override`, `_NoopContext`, `_EnvOverrideContext` 삭제.
  - 임포트에 `from src.llm.stage_config import StageLLMConfig` 추가.

- [ ] **Step 3: scripts/stock_report_prompt_tuning.py** — `with_model_override` import·사용 삭제. `--provider`/`--model` args는 실험 오버라이드로 유지하되 명시 주입으로 전환:

```python
llm_config = None
if args.model.strip():
    from src.llm.stage_config import StageLLMConfig
    from src.pipelines.stock_report.config import get_semantic_extraction_llm_config

    base = get_semantic_extraction_llm_config()
    llm_config = StageLLMConfig(
        provider=args.provider or base.provider,
        model=args.model.strip(),
        temperature=base.temperature,
    )
result = run_prompt_tuning_round(
    llm_config=llm_config,
    ...  # 기존 인자에서 provider= 만 제거
)
```

- [ ] **Step 4: test_tuning.py 수정** — `run_prompt_tuning_round(..., provider="openai", ...)` 2개 호출부에서 `provider="openai",` 줄 삭제. fake `classify_messages`가 `provider` kwarg를 받는다면 `llm_config` kwarg를 받도록 수정.

- [ ] **Step 5: 확인**

Run: `uv run pytest tests/pipelines/stock_report/ -q && grep -rn "with_model_override\|STOCK_REPORT_OPENAI_MODEL\|STOCK_REPORT_ANTHROPIC_MODEL\|STOCK_REPORT_SYNTHESIS" src/ scripts/ tests/ --include="*.py"`
Expected: 테스트 PASS, grep 출력 없음

- [ ] **Step 6: Commit**

```bash
git add src/pipelines/stock_report/ scripts/stock_report_prompt_tuning.py tests/pipelines/stock_report/
git commit -m "refactor: pdf/tuning paths use explicit StageLLMConfig injection"
```

---

### Task 8: CLI — --provider 제거, config 기반 LLM 주입

**Files:**
- Modify: `src/cli/main.py` (`analyze`, `brief`, `run_brief`, `run_deep_dive`, `report daily-v2`, `report ingest-pdf`)
- Test: `tests/cli/` 기존 회귀

**Interfaces:**
- Consumes: `resolve_stage_llm("analyze")`, `resolve_stage_llm("brief")` (Task 2); `run_daily_v2`/`run_ingest_pdf` 새 시그니처 (Task 6·7)
- Produces: `run_deep_dive(ticker_or_name: str) -> dict`, `run_brief(use_llm: bool) -> dict`

주의: `report ticker`(`run_daily_report`)의 `--provider`는 범위 밖 — 건드리지 않는다.

- [ ] **Step 1: run_deep_dive 수정** (`src/cli/main.py:264-325`)

```python
async def run_deep_dive(ticker_or_name: str) -> dict:
    """Run deep dive analysis pipeline."""
    # Resolve ticker if company name is provided
    ticker = await resolve_ticker(ticker_or_name)

    llm_config = resolve_stage_llm("analyze")
    is_openai = llm_config.provider == "openai"
    api_key_env = "OPENAI_API_KEY" if is_openai else "ANTHROPIC_API_KEY"
    base_url_env = "OPENAI_BASE_URL" if is_openai else "ANTHROPIC_BASE_URL"
    api_key = os.getenv(api_key_env)
    base_url = os.getenv(base_url_env)
    if not api_key:
        raise ValueError(f"Missing {api_key_env} environment variable")
```

LLM 생성부(기존 line 320-325):

```python
    llm = LLMProvider.create(
        provider=llm_config.provider,
        api_key=api_key,
        model=llm_config.model,
        base_url=base_url,
        temperature=llm_config.temperature,
    )
```

파일 상단 import에 추가: `from src.llm.stage_config import resolve_stage_llm`

- [ ] **Step 2: analyze 커맨드에서 --provider 삭제**

```python
@app.command()
def analyze(
    query: str = typer.Argument(..., help="Stock ticker or company name (e.g., AAPL, Apple, 구글)"),
):
```

호출부: `result = asyncio.run(run_deep_dive(query, provider))` → `result = asyncio.run(run_deep_dive(query))`

- [ ] **Step 3: brief 커맨드/run_brief 수정** — `brief()`에서 provider 옵션 삭제, `run_brief(provider, use_llm=...)` → `run_brief(use_llm=...)`. `run_brief(provider: str, use_llm: bool)` → `run_brief(use_llm: bool)`. LLM 생성부:

```python
    llm = None
    if use_llm:
        try:
            llm_config = resolve_stage_llm("brief")
            llm = llm_config.create_llm()
        except Exception as e:
            console.print(f"[yellow]LLM 초기화 실패 — 규칙 원문으로 진행: {e}[/yellow]")
```

- [ ] **Step 4: report daily-v2 / ingest-pdf에서 --provider 삭제** — `report_daily_v2()`의 `provider` 옵션 줄 삭제, `run_daily_v2(...)` 호출에서 `provider=provider,` 줄 삭제. `report_ingest_pdf()`의 `provider` 옵션 줄 삭제, `run_ingest_pdf(...)` 호출에서 `provider=provider,` 줄 삭제.

- [ ] **Step 5: 확인**

Run: `uv run pytest tests/cli/ -q && uv run jarvis analyze --help && uv run jarvis report daily-v2 --help`
Expected: 테스트 PASS, help 출력에 `--provider` 없음

- [ ] **Step 6: Commit**

```bash
git add src/cli/main.py tests/cli/
git commit -m "feat: CLI reads LLM config from config.yaml, drop --provider"
```

---

### Task 9: 문서 갱신 + 전체 검증

**Files:**
- Modify: `docs/CLI_USAGE.md`, `.claude/skills/jarvis-analyze/SKILL.md` (+ `.agents/skills/`에 동일 파일 있으면 함께)
- Modify: `docs/superpowers/specs/2026-07-24-llm-model-config-design.md` (상태를 "구현 완료"로)

- [ ] **Step 1: docs/CLI_USAGE.md** — `--provider` 옵션 설명·예시 제거 (line 75, 83, 249, 353 부근; 단 `report ticker` 관련이면 유지). "LLM 모델 설정" 절을 추가해 config.yaml `llm:` 섹션 스키마와 defaults 상속 규칙을 문서화.

- [ ] **Step 2: 스킬 문서** — `.claude/skills/jarvis-analyze/SKILL.md`에서 `[--provider openai|anthropic]`와 `--provider anthropic` 예시 제거. `grep -rn "provider" .claude/skills/ .agents/skills/`로 다른 잔재 확인.

- [ ] **Step 3: 전체 테스트 + 린트**

Run: `uv run pytest -q && uv run ruff check src/ tests/ scripts/`
Expected: 전부 PASS, 린트 클린 (베이스라인: 1238 passed)

- [ ] **Step 4: 스모크 체크 (외부 API·비용 발생 — 사용자 확인 후)** — `uv run jarvis report daily-v2 --help` 수준을 넘는 실제 실행(`jarvis report daily` 등)은 OpenAI 비용이 발생하므로 사용자에게 확인받고 실행한다. daily_report는 Bedrock Haiku → OpenAI 전환이므로 리포트 품질을 한 번 눈으로 확인할 것.

- [ ] **Step 5: Commit**

```bash
git add docs/ .claude/skills/ .agents/skills/
git commit -m "docs: document config.yaml llm section, drop --provider mentions"
```

---

## Self-Review 결과

- 스펙 커버리지: 스키마(Task 1·3), 중복 제거(Task 2), daily 스테이지별 모델/temperature(Task 1·3·4), daily_v2(Task 5·6), analyze/brief(Task 8), env 체인·--provider 삭제(Task 5·7·8), 문서(Task 9) — 전부 매핑됨.
- 타입 일관성: `StageLLMConfig`는 Task 2에서 단일 정의, 이후 전부 `src.llm.stage_config`에서 import. `classify_messages`/`run_prompt_tuning_round`의 `llm_config` kwarg 이름 통일 확인.
- 주의점: Task 5 완료 시점에 전체 테스트가 일시적으로 깨진다(호출부는 Task 6·7에서 정리) — Task 5~7은 연속 실행할 것.
