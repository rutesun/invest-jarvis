from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel


class CacheConfig(BaseModel):
    quote_ttl: int = 60
    history_ttl: int = 300
    indicators_ttl: int = 300


class TechnicalConfig(BaseModel):
    strategies: list[str] = ["trend"]


class AppConfig(BaseModel):
    technical: TechnicalConfig = TechnicalConfig()
    cache: CacheConfig = CacheConfig()


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    """Load configuration from YAML file or use defaults."""
    if config_path is None:
        config_path = Path("config.yaml")

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return AppConfig(**data)

    return AppConfig()
