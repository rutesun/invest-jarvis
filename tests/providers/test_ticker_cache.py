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


def test_cache_save_new_mapping():
    """Test saving new mapping to cache"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        cache = UserMappingCache(cache_path)

        cache.save('Apple', 'AAPL', 'Apple Inc.')

        # Verify in memory
        mapping = cache.get('Apple')
        assert mapping is not None
        assert mapping.ticker == 'AAPL'
        assert mapping.use_count == 1

        # Verify persisted
        cache2 = UserMappingCache(cache_path)
        mapping2 = cache2.get('Apple')
        assert mapping2 is not None
        assert mapping2.ticker == 'AAPL'


def test_cache_update_usage():
    """Test updating usage statistics"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        cache = UserMappingCache(cache_path)

        cache.save('Apple', 'AAPL', 'Apple Inc.')
        initial_count = cache.get('Apple').use_count
        initial_time = cache.get('Apple').last_used

        import time
        time.sleep(0.1)
        cache.update_usage('Apple')

        updated = cache.get('Apple')
        assert updated.use_count == initial_count + 1
        assert updated.last_used > initial_time
