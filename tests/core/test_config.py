def test_load_config_from_yaml(tmp_path):
    config_content = """
technical:
  strategies:
    - trend
    - oscillator
cache:
  quote_ttl: 60
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    from src.core.config import load_config

    config = load_config(config_file)

    assert config.technical.strategies == ["trend", "oscillator"]
    assert config.cache.quote_ttl == 60


def test_load_config_default():
    from src.core.config import AppConfig, load_config

    config = load_config(None)
    assert isinstance(config, AppConfig)
    assert config.cache.quote_ttl == 60
