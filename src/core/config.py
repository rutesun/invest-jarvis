from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CacheConfig(BaseModel):
    quote_ttl: int = 60
    history_ttl: int = 300
    indicators_ttl: int = 300


class TechnicalConfig(BaseModel):
    strategies: list[str] = ["trend"]


class LLMEntryConfig(BaseModel):
    """파이프라인/스테이지별 부분 오버라이드 — 명시한 필드만 defaults를 덮는다."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["openai", "anthropic"] | None = None
    model: str | None = Field(default=None, min_length=1)
    temperature: float | None = None


class LLMDefaultsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["openai", "anthropic"] = "openai"
    model: str = "gpt-5.6-terra"
    temperature: float = 0.0


class ResolvedLLMEntry(BaseModel):
    provider: str
    model: str = Field(min_length=1)
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
    model_config = ConfigDict(extra="forbid")

    defaults: LLMDefaultsConfig = LLMDefaultsConfig()
    daily: dict[str, LLMEntryConfig] = Field(default_factory=_default_daily)
    daily_v2: dict[str, LLMEntryConfig] = Field(default_factory=_default_daily_v2)
    analyze: LLMEntryConfig = LLMEntryConfig()
    brief: LLMEntryConfig = LLMEntryConfig()

    @model_validator(mode="after")
    def _merge_stage_dicts_and_reject_unknown_keys(self) -> "LLMConfig":
        # Merge provided stage entries over the code defaults so that omitted
        # sibling stages still carry their stage-specific defaults.
        self.daily = {**_default_daily(), **self.daily}
        self.daily_v2 = {**_default_daily_v2(), **self.daily_v2}

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
