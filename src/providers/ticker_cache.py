from pathlib import Path
from typing import Optional
import yaml
from datetime import datetime, timedelta
from src.providers.ticker_models import CachedMapping


class UserMappingCache:
    """Manages user ticker mapping cache"""

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        max_entries: int = 200,
        expiry_days: int = 180
    ):
        self.cache_path = cache_path or self._default_cache_path()
        self.max_entries = max_entries
        self.expiry_days = expiry_days
        self.mappings: dict[str, CachedMapping] = {}

        self._load()

    def _default_cache_path(self) -> Path:
        """Get default cache path"""
        return Path.home() / ".cache/invest-jarvis/user_mappings.yaml"

    def _load(self):
        """Load cache from disk"""
        if not self.cache_path.exists():
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._save()
            return

        try:
            with open(self.cache_path, 'r') as f:
                data = yaml.safe_load(f) or {}

            mappings_data = data.get('mappings', {})
            for query, mapping_dict in mappings_data.items():
                self.mappings[query] = CachedMapping(
                    ticker=mapping_dict['ticker'],
                    display_name=mapping_dict['display_name'],
                    created_at=datetime.fromisoformat(mapping_dict['created_at']),
                    last_used=datetime.fromisoformat(mapping_dict['last_used']),
                    use_count=mapping_dict['use_count']
                )
        except Exception:
            # If corrupted, start fresh
            self.mappings = {}
            self._save()

    def _save(self):
        """Save cache to disk"""
        data = {
            'version': 1,
            'last_cleanup': datetime.now().isoformat(),
            'mappings': {}
        }

        for query, mapping in self.mappings.items():
            data['mappings'][query] = {
                'ticker': mapping.ticker,
                'display_name': mapping.display_name,
                'created_at': mapping.created_at.isoformat(),
                'last_used': mapping.last_used.isoformat(),
                'use_count': mapping.use_count
            }

        with open(self.cache_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)

    def get(self, query: str) -> Optional[CachedMapping]:
        """Get cached mapping if exists"""
        return self.mappings.get(query)

    def save(self, query: str, ticker: str, display_name: str):
        """Save new mapping or update existing"""
        now = datetime.now()

        if query in self.mappings:
            # Update existing
            mapping = self.mappings[query]
            mapping.ticker = ticker
            mapping.display_name = display_name
            mapping.last_used = now
            mapping.use_count += 1
        else:
            # Create new
            self.mappings[query] = CachedMapping(
                ticker=ticker,
                display_name=display_name,
                created_at=now,
                last_used=now,
                use_count=1
            )

        self._save()

    def update_usage(self, query: str):
        """Update last_used and increment use_count"""
        if query in self.mappings:
            mapping = self.mappings[query]
            mapping.last_used = datetime.now()
            mapping.use_count += 1
            self._save()

    def cleanup_old_entries(self):
        """Remove stale entries and enforce LRU limit"""
        now = datetime.now()
        cutoff = now - timedelta(days=self.expiry_days)

        # Remove entries not used within expiry_days
        self.mappings = {
            k: v for k, v in self.mappings.items()
            if v.last_used > cutoff
        }

        # Enforce max_entries via LRU
        if len(self.mappings) > self.max_entries:
            sorted_entries = sorted(
                self.mappings.items(),
                key=lambda x: x[1].last_used,
                reverse=True
            )
            self.mappings = dict(sorted_entries[:self.max_entries])

        self._save()

    def list_mappings(self) -> list[dict]:
        """Return all cached mappings as list of dicts"""
        result = []
        for query, mapping in sorted(
            self.mappings.items(),
            key=lambda x: x[1].use_count,
            reverse=True
        ):
            result.append({
                'query': query,
                'ticker': mapping.ticker,
                'display_name': mapping.display_name,
                'use_count': mapping.use_count,
                'last_used': mapping.last_used
            })
        return result

    def evict(self, query: str):
        """Remove a single cached mapping by query key."""
        if query in self.mappings:
            del self.mappings[query]
            self._save()

    def clear(self):
        """Clear all cached mappings"""
        self.mappings = {}
        self._save()
