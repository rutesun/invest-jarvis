import pytest
from pathlib import Path
import tempfile
import yaml
from src.providers.ticker_cache import UserMappingCache


def test_cache_init_creates_file():
    """Test cache creates file if not exists"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        cache = UserMappingCache(cache_path)

        assert cache_path.exists()
        assert cache.cache_path == cache_path


def test_cache_init_loads_existing():
    """Test cache loads existing file"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"

        # Create existing cache file
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'w') as f:
            yaml.dump({
                'version': 1,
                'mappings': {
                    'Apple': {
                        'ticker': 'AAPL',
                        'display_name': 'Apple Inc.',
                        'created_at': '2026-04-09T10:00:00',
                        'last_used': '2026-04-09T10:00:00',
                        'use_count': 1
                    }
                }
            }, f)

        cache = UserMappingCache(cache_path)
        mapping = cache.get('Apple')
        assert mapping is not None
        assert mapping.ticker == 'AAPL'
