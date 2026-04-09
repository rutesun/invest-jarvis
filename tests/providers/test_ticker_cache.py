import pytest
from pathlib import Path
import tempfile
import yaml
from datetime import datetime, timedelta
from src.providers.ticker_cache import UserMappingCache
from src.providers.ticker_models import CachedMapping


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


def test_cache_cleanup_old_entries():
    """Test cleanup removes entries older than expiry_days"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        cache = UserMappingCache(cache_path, expiry_days=1)

        # Create old entry
        old_time = datetime.now() - timedelta(days=2)
        cache.mappings['old'] = CachedMapping(
            ticker='OLD',
            display_name='Old Stock',
            created_at=old_time,
            last_used=old_time,
            use_count=1
        )

        # Create recent entry
        cache.save('recent', 'NEW', 'New Stock')

        cache.cleanup_old_entries()

        assert 'old' not in cache.mappings
        assert 'recent' in cache.mappings


def test_cache_cleanup_enforces_max_entries():
    """Test cleanup enforces max_entries limit via LRU"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        cache = UserMappingCache(cache_path, max_entries=3)

        # Add 5 entries
        for i in range(5):
            cache.save(f'query{i}', f'TICK{i}', f'Stock {i}')
            if i < 4:
                import time
                time.sleep(0.01)  # Ensure different timestamps

        cache.cleanup_old_entries()

        # Should keep only 3 most recent
        assert len(cache.mappings) == 3
        assert 'query4' in cache.mappings  # Most recent
        assert 'query3' in cache.mappings
        assert 'query2' in cache.mappings
        assert 'query0' not in cache.mappings  # Oldest removed
