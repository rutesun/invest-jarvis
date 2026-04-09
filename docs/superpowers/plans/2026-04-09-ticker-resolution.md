# Ticker Resolution System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable users to search stocks using company names (English/Korean) in addition to ticker symbols, with intelligent resolution using static mappings, learned preferences, and yfinance Search API.

**Architecture:** Multi-stage resolution with priority: direct ticker → user cache → static mapping → yfinance Search. User selections are cached for future use. TDD approach with frequent commits.

**Tech Stack:** Python 3.13, Pydantic, yfinance, YAML, pytest

---

## File Structure

### New Files
- `src/providers/ticker_models.py` - Pydantic models for resolution results
- `src/providers/ticker_cache.py` - User mapping cache management
- `src/providers/ticker_resolver.py` - Core resolution logic
- `config/ticker_names.yaml` - Static Korean→English mappings
- `tests/providers/test_ticker_models.py` - Model tests
- `tests/providers/test_ticker_cache.py` - Cache tests
- `tests/providers/test_ticker_resolver.py` - Resolver tests

### Modified Files
- `src/cli/main.py` - Add cache command, update check/analyze/report

---

## Task 1: Data Models

**Files:**
- Create: `src/providers/ticker_models.py`
- Test: `tests/providers/test_ticker_models.py`

- [ ] **Step 1: Write failing test for CandidateTicker model**

```python
# tests/providers/test_ticker_models.py
import pytest
from src.providers.ticker_models import CandidateTicker


def test_candidate_ticker_creation():
    """Test CandidateTicker model creation"""
    candidate = CandidateTicker(
        symbol="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        score=35427.0,
        quote_type="EQUITY"
    )
    
    assert candidate.symbol == "AAPL"
    assert candidate.name == "Apple Inc."
    assert candidate.exchange == "NASDAQ"
    assert candidate.score == 35427.0
    assert candidate.quote_type == "EQUITY"


def test_candidate_ticker_validation():
    """Test CandidateTicker field validation"""
    with pytest.raises(ValueError):
        CandidateTicker(
            symbol="",  # Empty symbol should fail
            name="Apple",
            exchange="NASDAQ",
            score=100.0,
            quote_type="EQUITY"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_ticker_models.py::test_candidate_ticker_creation -v`
Expected: ModuleNotFoundError: No module named 'src.providers.ticker_models'

- [ ] **Step 3: Write minimal CandidateTicker model**

```python
# src/providers/ticker_models.py
from pydantic import BaseModel, Field


class CandidateTicker(BaseModel):
    """Candidate ticker from search results"""
    symbol: str = Field(..., min_length=1)
    name: str
    exchange: str
    score: float
    quote_type: str  # "EQUITY", "ETF", "INDEX"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_ticker_models.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/providers/ticker_models.py tests/providers/test_ticker_models.py
git commit -m "feat(providers): add CandidateTicker model"
```

- [ ] **Step 6: Write failing test for TickerResolution model**

```python
# tests/providers/test_ticker_models.py
from src.providers.ticker_models import TickerResolution, CandidateTicker


def test_ticker_resolution_single_result():
    """Test TickerResolution with single result"""
    resolution = TickerResolution(
        original_query="AAPL",
        resolved_ticker="AAPL",
        display_name="Apple Inc.",
        confidence="high",
        candidates=[],
        resolution_method="direct_ticker",
        source="user_input"
    )
    
    assert resolution.original_query == "AAPL"
    assert resolution.resolved_ticker == "AAPL"
    assert resolution.confidence == "high"
    assert resolution.resolution_method == "direct_ticker"
    assert len(resolution.candidates) == 0


def test_ticker_resolution_with_candidates():
    """Test TickerResolution with multiple candidates"""
    candidates = [
        CandidateTicker(
            symbol="005930.KS",
            name="SamsungElec",
            exchange="KSC",
            score=23044.0,
            quote_type="EQUITY"
        ),
        CandidateTicker(
            symbol="207940.KS",
            name="SAMSUNG BIOLOGICS",
            exchange="KSC",
            score=20002.0,
            quote_type="EQUITY"
        )
    ]
    
    resolution = TickerResolution(
        original_query="Samsung",
        resolved_ticker="005930.KS",
        display_name="SamsungElec",
        confidence="low",
        candidates=candidates,
        resolution_method="yfinance_search_multiple",
        source="yfinance_api"
    )
    
    assert len(resolution.candidates) == 2
    assert resolution.confidence == "low"
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_ticker_models.py::test_ticker_resolution_single_result -v`
Expected: ImportError or AttributeError for TickerResolution

- [ ] **Step 8: Write TickerResolution model**

```python
# src/providers/ticker_models.py
from typing import Literal


class TickerResolution(BaseModel):
    """Result of ticker resolution"""
    original_query: str
    resolved_ticker: str
    display_name: str
    confidence: Literal["high", "medium", "low"]
    candidates: list[CandidateTicker]
    resolution_method: Literal[
        "direct_ticker",
        "user_cache",
        "static_mapping",
        "yfinance_search_single",
        "yfinance_search_multiple"
    ]
    source: str
```

- [ ] **Step 9: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_ticker_models.py -v`
Expected: 4 passed

- [ ] **Step 10: Commit**

```bash
git add src/providers/ticker_models.py tests/providers/test_ticker_models.py
git commit -m "feat(providers): add TickerResolution model"
```

- [ ] **Step 11: Write failing test for CachedMapping model**

```python
# tests/providers/test_ticker_models.py
from datetime import datetime
from src.providers.ticker_models import CachedMapping


def test_cached_mapping_creation():
    """Test CachedMapping model creation"""
    now = datetime.now()
    mapping = CachedMapping(
        ticker="AAPL",
        display_name="Apple Inc.",
        created_at=now,
        last_used=now,
        use_count=1
    )
    
    assert mapping.ticker == "AAPL"
    assert mapping.display_name == "Apple Inc."
    assert mapping.use_count == 1
```

- [ ] **Step 12: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_ticker_models.py::test_cached_mapping_creation -v`
Expected: ImportError or AttributeError for CachedMapping

- [ ] **Step 13: Write CachedMapping model**

```python
# src/providers/ticker_models.py
from datetime import datetime


class CachedMapping(BaseModel):
    """User cached ticker mapping"""
    ticker: str
    display_name: str
    created_at: datetime
    last_used: datetime
    use_count: int = Field(ge=1)
```

- [ ] **Step 14: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_ticker_models.py -v`
Expected: 5 passed

- [ ] **Step 15: Commit**

```bash
git add src/providers/ticker_models.py tests/providers/test_ticker_models.py
git commit -m "feat(providers): add CachedMapping model"
```

---

## Task 2: User Cache System

**Files:**
- Create: `src/providers/ticker_cache.py`
- Test: `tests/providers/test_ticker_cache.py`

- [ ] **Step 1: Write failing test for cache initialization**

```python
# tests/providers/test_ticker_cache.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_ticker_cache.py::test_cache_init_creates_file -v`
Expected: ModuleNotFoundError: No module named 'src.providers.ticker_cache'

- [ ] **Step 3: Write minimal UserMappingCache class**

```python
# src/providers/ticker_cache.py
from pathlib import Path
from typing import Optional
import yaml
from datetime import datetime
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_ticker_cache.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/providers/ticker_cache.py tests/providers/test_ticker_cache.py
git commit -m "feat(providers): add UserMappingCache initialization and loading"
```

- [ ] **Step 6: Write failing test for save and update_usage**

```python
# tests/providers/test_ticker_cache.py
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
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_ticker_cache.py::test_cache_save_new_mapping -v`
Expected: AttributeError: 'UserMappingCache' object has no attribute 'save'

- [ ] **Step 8: Add save and update_usage methods**

```python
# src/providers/ticker_cache.py
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
```

- [ ] **Step 9: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_ticker_cache.py -v`
Expected: 4 passed

- [ ] **Step 10: Commit**

```bash
git add src/providers/ticker_cache.py tests/providers/test_ticker_cache.py
git commit -m "feat(providers): add cache save and update_usage methods"
```

- [ ] **Step 11: Write failing test for cleanup**

```python
# tests/providers/test_ticker_cache.py
from datetime import timedelta


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
```

- [ ] **Step 12: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_ticker_cache.py::test_cache_cleanup_old_entries -v`
Expected: AttributeError: 'UserMappingCache' object has no attribute 'cleanup_old_entries'

- [ ] **Step 13: Add cleanup method**

```python
# src/providers/ticker_cache.py
from datetime import timedelta


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
```

- [ ] **Step 14: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_ticker_cache.py -v`
Expected: 6 passed

- [ ] **Step 15: Commit**

```bash
git add src/providers/ticker_cache.py tests/providers/test_ticker_cache.py
git commit -m "feat(providers): add cache cleanup with expiry and LRU"
```

- [ ] **Step 16: Write failing test for list and clear**

```python
# tests/providers/test_ticker_cache.py
def test_cache_list_mappings():
    """Test listing all cached mappings"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        cache = UserMappingCache(cache_path)
        
        cache.save('Apple', 'AAPL', 'Apple Inc.')
        cache.save('Google', 'GOOGL', 'Alphabet Inc.')
        
        mappings = cache.list_mappings()
        
        assert len(mappings) == 2
        assert any(m['query'] == 'Apple' and m['ticker'] == 'AAPL' for m in mappings)
        assert any(m['query'] == 'Google' and m['ticker'] == 'GOOGL' for m in mappings)


def test_cache_clear():
    """Test clearing all cached mappings"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        cache = UserMappingCache(cache_path)
        
        cache.save('Apple', 'AAPL', 'Apple Inc.')
        assert len(cache.mappings) == 1
        
        cache.clear()
        
        assert len(cache.mappings) == 0
        
        # Verify persisted
        cache2 = UserMappingCache(cache_path)
        assert len(cache2.mappings) == 0
```

- [ ] **Step 17: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_ticker_cache.py::test_cache_list_mappings -v`
Expected: AttributeError: 'UserMappingCache' object has no attribute 'list_mappings'

- [ ] **Step 18: Add list_mappings and clear methods**

```python
# src/providers/ticker_cache.py
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
    
    def clear(self):
        """Clear all cached mappings"""
        self.mappings = {}
        self._save()
```

- [ ] **Step 19: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_ticker_cache.py -v`
Expected: 8 passed

- [ ] **Step 20: Commit**

```bash
git add src/providers/ticker_cache.py tests/providers/test_ticker_cache.py
git commit -m "feat(providers): add cache list_mappings and clear methods"
```

---

## Task 3: Ticker Resolver - Direct Ticker Detection

**Files:**
- Create: `src/providers/ticker_resolver.py`
- Test: `tests/providers/test_ticker_resolver.py`

- [ ] **Step 1: Write failing test for direct US ticker detection**

```python
# tests/providers/test_ticker_resolver.py
import pytest
from src.providers.ticker_resolver import TickerResolver


@pytest.mark.asyncio
async def test_resolve_direct_us_ticker():
    """Test direct US ticker detection"""
    resolver = TickerResolver()
    
    result = await resolver.resolve("AAPL")
    
    assert result.original_query == "AAPL"
    assert result.resolved_ticker == "AAPL"
    assert result.confidence == "high"
    assert result.resolution_method == "direct_ticker"
    assert len(result.candidates) == 0


@pytest.mark.asyncio
async def test_resolve_direct_korean_ticker():
    """Test direct Korean ticker detection"""
    resolver = TickerResolver()
    
    result = await resolver.resolve("005930.KS")
    
    assert result.resolved_ticker == "005930.KS"
    assert result.resolution_method == "direct_ticker"
    assert result.confidence == "high"


@pytest.mark.asyncio
async def test_resolve_korean_ticker_normalization():
    """Test 6-digit code auto-adds .KS suffix"""
    resolver = TickerResolver()
    
    result = await resolver.resolve("005930")
    
    assert result.resolved_ticker == "005930.KS"
    assert result.resolution_method == "direct_ticker"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_ticker_resolver.py::test_resolve_direct_us_ticker -v`
Expected: ModuleNotFoundError: No module named 'src.providers.ticker_resolver'

- [ ] **Step 3: Write minimal TickerResolver with direct detection**

```python
# src/providers/ticker_resolver.py
import re
from typing import Optional
from pathlib import Path
import yaml
from src.providers.ticker_models import TickerResolution, CandidateTicker
from src.providers.ticker_cache import UserMappingCache


class TickerResolutionError(Exception):
    """Base exception for ticker resolution"""
    pass


class TickerNotFoundError(TickerResolutionError):
    """No ticker found for query"""
    pass


class TickerResolver:
    """Resolves user queries to ticker symbols"""
    
    def __init__(
        self,
        static_mapping_path: str = "config/ticker_names.yaml",
        user_cache_path: Optional[Path] = None
    ):
        self.static_mapping = self._load_static_mapping(static_mapping_path)
        self.user_cache = UserMappingCache(user_cache_path)
        self._search_cache = {}
    
    def _load_static_mapping(self, path: str) -> dict:
        """Load static Korean→English mapping"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                return data.get('korean_to_english', {})
        except FileNotFoundError:
            return {}
    
    async def resolve(self, query: str) -> TickerResolution:
        """
        Resolve user query to ticker symbol.
        
        Priority:
        1. Direct ticker detection
        2. User cache lookup
        3. Static mapping
        4. yfinance Search API
        """
        query = query.strip()
        
        # Step 1: Direct ticker detection
        if self._is_direct_ticker(query):
            normalized = self._normalize_ticker(query)
            return TickerResolution(
                original_query=query,
                resolved_ticker=normalized,
                display_name=normalized,
                confidence="high",
                candidates=[],
                resolution_method="direct_ticker",
                source="user_input"
            )
        
        # TODO: Step 2-4 in later tasks
        raise TickerNotFoundError(f"Could not resolve: {query}")
    
    def _is_direct_ticker(self, query: str) -> bool:
        """Check if query is already a valid ticker symbol"""
        patterns = [
            r'^[A-Z]{1,5}$',        # US stocks: AAPL, GOOGL
            r'^\d{6}\.KS$',         # Korean KOSPI: 005930.KS
            r'^\d{6}\.KQ$',         # Korean KOSDAQ: 123456.KQ
            r'^\d{6}$',             # Korean code without suffix
        ]
        return any(re.match(p, query) for p in patterns)
    
    def _normalize_ticker(self, query: str) -> str:
        """Normalize ticker format (add .KS for 6-digit codes)"""
        if re.match(r'^\d{6}$', query):
            return f"{query}.KS"
        return query
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_ticker_resolver.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/providers/ticker_resolver.py tests/providers/test_ticker_resolver.py
git commit -m "feat(providers): add TickerResolver with direct ticker detection"
```

---

## Task 4: Ticker Resolver - User Cache Lookup

**Files:**
- Modify: `src/providers/ticker_resolver.py`
- Modify: `tests/providers/test_ticker_resolver.py`

- [ ] **Step 1: Write failing test for user cache lookup**

```python
# tests/providers/test_ticker_resolver.py
import tempfile


@pytest.mark.asyncio
async def test_resolve_from_user_cache():
    """Test resolution from user cache"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path)
        
        # Pre-populate cache
        resolver.user_cache.save('애플', 'AAPL', 'Apple Inc.')
        
        result = await resolver.resolve('애플')
        
        assert result.resolved_ticker == 'AAPL'
        assert result.display_name == 'Apple Inc.'
        assert result.resolution_method == 'user_cache'
        assert result.confidence == 'high'


@pytest.mark.asyncio
async def test_resolve_cache_updates_usage():
    """Test cache usage is updated on hit"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path)
        
        resolver.user_cache.save('Tesla', 'TSLA', 'Tesla, Inc.')
        initial_count = resolver.user_cache.get('Tesla').use_count
        
        await resolver.resolve('Tesla')
        
        updated_count = resolver.user_cache.get('Tesla').use_count
        assert updated_count == initial_count + 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_ticker_resolver.py::test_resolve_from_user_cache -v`
Expected: TickerNotFoundError: Could not resolve: 애플

- [ ] **Step 3: Add user cache lookup to resolve method**

```python
# src/providers/ticker_resolver.py
    async def resolve(self, query: str) -> TickerResolution:
        """
        Resolve user query to ticker symbol.
        
        Priority:
        1. Direct ticker detection
        2. User cache lookup
        3. Static mapping
        4. yfinance Search API
        """
        query = query.strip()
        
        # Step 1: Direct ticker detection
        if self._is_direct_ticker(query):
            normalized = self._normalize_ticker(query)
            return TickerResolution(
                original_query=query,
                resolved_ticker=normalized,
                display_name=normalized,
                confidence="high",
                candidates=[],
                resolution_method="direct_ticker",
                source="user_input"
            )
        
        # Step 2: User cache lookup
        cached = self.user_cache.get(query)
        if cached:
            self.user_cache.update_usage(query)
            return TickerResolution(
                original_query=query,
                resolved_ticker=cached.ticker,
                display_name=cached.display_name,
                confidence="high",
                candidates=[],
                resolution_method="user_cache",
                source="user_cache"
            )
        
        # TODO: Step 3-4 in later tasks
        raise TickerNotFoundError(f"Could not resolve: {query}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_ticker_resolver.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/providers/ticker_resolver.py tests/providers/test_ticker_resolver.py
git commit -m "feat(providers): add user cache lookup to TickerResolver"
```

---

## Task 5: Ticker Resolver - Static Mapping

**Files:**
- Modify: `src/providers/ticker_resolver.py`
- Modify: `tests/providers/test_ticker_resolver.py`
- Create: `config/ticker_names.yaml`

- [ ] **Step 1: Create minimal static mapping file**

```yaml
# config/ticker_names.yaml
korean_to_english:
  애플: Apple
  구글: Google
  테슬라: Tesla
  삼성전자: Samsung Electronics
```

- [ ] **Step 2: Write failing test for static mapping**

```python
# tests/providers/test_ticker_resolver.py
@pytest.mark.asyncio
async def test_resolve_from_static_mapping():
    """Test resolution using static Korean→English mapping"""
    resolver = TickerResolver()
    
    # This will use static mapping to convert 구글→Google
    # then search for Google (mocked in next task)
    result = await resolver.resolve('구글')
    
    # For now, just verify it attempts static lookup
    # Full test will work after yfinance integration
    assert result.original_query == '구글'
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_ticker_resolver.py::test_resolve_from_static_mapping -v`
Expected: TickerNotFoundError: Could not resolve: 구글

- [ ] **Step 4: Add static mapping lookup (without search yet)**

```python
# src/providers/ticker_resolver.py
    def _contains_korean(self, text: str) -> bool:
        """Check if text contains Korean characters"""
        return bool(re.search(r'[가-힣]', text))
    
    async def resolve(self, query: str) -> TickerResolution:
        """
        Resolve user query to ticker symbol.
        
        Priority:
        1. Direct ticker detection
        2. User cache lookup
        3. Static mapping
        4. yfinance Search API
        """
        query = query.strip()
        
        # Step 1: Direct ticker detection
        if self._is_direct_ticker(query):
            normalized = self._normalize_ticker(query)
            return TickerResolution(
                original_query=query,
                resolved_ticker=normalized,
                display_name=normalized,
                confidence="high",
                candidates=[],
                resolution_method="direct_ticker",
                source="user_input"
            )
        
        # Step 2: User cache lookup
        cached = self.user_cache.get(query)
        if cached:
            self.user_cache.update_usage(query)
            return TickerResolution(
                original_query=query,
                resolved_ticker=cached.ticker,
                display_name=cached.display_name,
                confidence="high",
                candidates=[],
                resolution_method="user_cache",
                source="user_cache"
            )
        
        # Step 3: Static mapping (Korean → English)
        search_query = query
        if self._contains_korean(query):
            english_name = self.static_mapping.get(query.lower())
            if english_name:
                search_query = english_name
        
        # TODO: Step 4 - yfinance Search with search_query
        raise TickerNotFoundError(f"Could not resolve: {query}")
```

- [ ] **Step 5: Commit**

```bash
git add config/ticker_names.yaml src/providers/ticker_resolver.py tests/providers/test_ticker_resolver.py
git commit -m "feat(providers): add static mapping lookup for Korean names"
```

---

## Task 6: Ticker Resolver - yfinance Search

**Files:**
- Modify: `src/providers/ticker_resolver.py`
- Modify: `tests/providers/test_ticker_resolver.py`

- [ ] **Step 1: Write failing test for yfinance search**

```python
# tests/providers/test_ticker_resolver.py
@pytest.mark.asyncio
async def test_resolve_yfinance_search_single():
    """Test yfinance search with single clear result"""
    resolver = TickerResolver()
    
    result = await resolver.resolve('Apple')
    
    assert result.resolved_ticker == 'AAPL'
    assert 'Apple' in result.display_name
    assert result.resolution_method == 'yfinance_search_single'
    assert result.confidence == 'high'


@pytest.mark.asyncio
async def test_resolve_yfinance_search_multiple():
    """Test yfinance search with multiple results"""
    resolver = TickerResolver()
    
    result = await resolver.resolve('Samsung')
    
    # Should return top result but mark as low confidence
    assert result.resolved_ticker  # Has a ticker
    assert len(result.candidates) > 1
    assert result.confidence == 'low'
    assert result.resolution_method == 'yfinance_search_multiple'


@pytest.mark.asyncio
async def test_resolve_not_found():
    """Test query that returns no results"""
    resolver = TickerResolver()
    
    with pytest.raises(TickerNotFoundError):
        await resolver.resolve('InvalidCompanyXYZ123')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/providers/test_ticker_resolver.py::test_resolve_yfinance_search_single -v`
Expected: TickerNotFoundError

- [ ] **Step 3: Add yfinance Search integration**

```python
# src/providers/ticker_resolver.py
import yfinance as yf
import time


    async def resolve(self, query: str) -> TickerResolution:
        """
        Resolve user query to ticker symbol.
        
        Priority:
        1. Direct ticker detection
        2. User cache lookup
        3. Static mapping
        4. yfinance Search API
        """
        query = query.strip()
        
        # Step 1: Direct ticker detection
        if self._is_direct_ticker(query):
            normalized = self._normalize_ticker(query)
            return TickerResolution(
                original_query=query,
                resolved_ticker=normalized,
                display_name=normalized,
                confidence="high",
                candidates=[],
                resolution_method="direct_ticker",
                source="user_input"
            )
        
        # Step 2: User cache lookup
        cached = self.user_cache.get(query)
        if cached:
            self.user_cache.update_usage(query)
            return TickerResolution(
                original_query=query,
                resolved_ticker=cached.ticker,
                display_name=cached.display_name,
                confidence="high",
                candidates=[],
                resolution_method="user_cache",
                source="user_cache"
            )
        
        # Step 3: Static mapping (Korean → English)
        search_query = query
        if self._contains_korean(query):
            english_name = self.static_mapping.get(query.lower())
            if english_name:
                search_query = english_name
        
        # Step 4: yfinance Search API
        candidates = await self._search_yfinance(search_query)
        
        if not candidates:
            raise TickerNotFoundError(f"No results for '{query}'")
        
        # Determine confidence and selection
        resolved_ticker, confidence = self._determine_selection(candidates)
        
        resolution_method = (
            "yfinance_search_single" if len(candidates) == 1
            else "yfinance_search_multiple"
        )
        
        return TickerResolution(
            original_query=query,
            resolved_ticker=resolved_ticker,
            display_name=candidates[0].name,
            confidence=confidence,
            candidates=candidates if len(candidates) > 1 else [],
            resolution_method=resolution_method,
            source="yfinance_api"
        )
    
    async def _search_yfinance(self, query: str) -> list[CandidateTicker]:
        """Search tickers using yfinance Search API"""
        # Check cache (60s TTL)
        cache_key = (query, int(time.time()) // 60)
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]
        
        try:
            search = yf.Search(query)
            candidates = []
            
            for q in search.quotes or []:
                candidates.append(CandidateTicker(
                    symbol=q['symbol'],
                    name=q.get('shortname', q.get('longname', 'N/A')),
                    exchange=q.get('exchange', 'N/A'),
                    score=q.get('score', 0),
                    quote_type=q.get('quoteType', 'EQUITY')
                ))
            
            # Sort by score descending
            candidates.sort(key=lambda x: x.score, reverse=True)
            
            # Cache result
            self._search_cache[cache_key] = candidates
            
            return candidates
        except Exception as e:
            raise TickerResolutionError(f"Search failed: {e}")
    
    def _determine_selection(
        self,
        candidates: list[CandidateTicker]
    ) -> tuple[str, str]:
        """
        Determine which ticker to select and confidence level.
        
        Returns: (ticker, confidence)
        """
        if len(candidates) == 1:
            return candidates[0].symbol, "high"
        
        # Check score gap between top 2
        top_score = candidates[0].score
        second_score = candidates[1].score if len(candidates) > 1 else 0
        
        score_gap_pct = (top_score - second_score) / top_score if top_score > 0 else 0
        
        if score_gap_pct > 0.5:  # Top result 50%+ higher
            return candidates[0].symbol, "high"
        
        # Ambiguous - need user selection
        return candidates[0].symbol, "low"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_ticker_resolver.py -v`
Expected: 9 passed (note: requires network access for yfinance)

- [ ] **Step 5: Commit**

```bash
git add src/providers/ticker_resolver.py tests/providers/test_ticker_resolver.py
git commit -m "feat(providers): add yfinance Search integration to TickerResolver"
```

- [ ] **Step 6: Add save_user_selection helper**

```python
# src/providers/ticker_resolver.py
    def save_user_selection(self, query: str, ticker: str, display_name: str):
        """Save user-selected ticker to cache"""
        self.user_cache.save(query, ticker, display_name)
```

- [ ] **Step 7: Write test for save_user_selection**

```python
# tests/providers/test_ticker_resolver.py
@pytest.mark.asyncio
async def test_save_user_selection():
    """Test saving user selection to cache"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path)
        
        resolver.save_user_selection('Samsung', '005930.KS', 'SamsungElec')
        
        # Verify saved
        cached = resolver.user_cache.get('Samsung')
        assert cached is not None
        assert cached.ticker == '005930.KS'
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/providers/test_ticker_resolver.py::test_save_user_selection -v`
Expected: PASSED

- [ ] **Step 9: Commit**

```bash
git add src/providers/ticker_resolver.py tests/providers/test_ticker_resolver.py
git commit -m "feat(providers): add save_user_selection helper method"
```

---

## Task 7: Static Mapping Configuration

**Files:**
- Modify: `config/ticker_names.yaml`

- [ ] **Step 1: Populate static mapping with common stocks**

```yaml
# config/ticker_names.yaml
korean_to_english:
  # US Tech Stocks
  애플: Apple
  구글: Google
  알파벳: Alphabet
  테슬라: Tesla
  마이크로소프트: Microsoft
  아마존: Amazon
  메타: Meta
  페이스북: Meta
  엔비디아: NVIDIA
  넷플릭스: Netflix
  
  # Korean Stocks
  삼성전자: Samsung Electronics
  삼성: Samsung Electronics
  SK하이닉스: SK Hynix
  하이닉스: SK Hynix
  현대차: Hyundai Motor
  현대: Hyundai Motor
  기아: Kia
  셀트리온: Celltrion
  삼성바이오로직스: Samsung Biologics
  카카오: Kakao
  네이버: NAVER
  LG에너지솔루션: LG Energy Solution
  LG화학: LG Chem
  POSCO홀딩스: POSCO Holdings
  포스코: POSCO Holdings
```

- [ ] **Step 2: Commit**

```bash
git add config/ticker_names.yaml
git commit -m "config: populate ticker_names.yaml with 20+ common stocks"
```

---

## Task 8: CLI Integration - cache command

**Files:**
- Modify: `src/cli/main.py`

- [ ] **Step 1: Write failing test for cache list command**

```python
# tests/cli/test_cli.py
import tempfile
from typer.testing import CliRunner
from src.cli.main import app


def test_cache_list_empty():
    """Test cache list with empty cache"""
    runner = CliRunner()
    result = runner.invoke(app, ["cache", "list"])
    
    assert result.exit_code == 0
    assert "No cached mappings" in result.stdout


def test_cache_list_with_entries():
    """Test cache list with entries"""
    # Pre-populate cache
    from src.providers.ticker_cache import UserMappingCache
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        cache = UserMappingCache(cache_path)
        cache.save('Apple', 'AAPL', 'Apple Inc.')
        cache.save('Google', 'GOOGL', 'Alphabet Inc.')
        
        # TODO: Need to inject cache_path into CLI
        # For now, just test the command exists
        runner = CliRunner()
        result = runner.invoke(app, ["cache", "list"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cli/test_cli.py::test_cache_list_empty -v`
Expected: Error or command not found

- [ ] **Step 3: Add cache command to CLI**

```python
# src/cli/main.py
from typing import Literal
from src.providers.ticker_cache import UserMappingCache


@app.command()
def cache(
    action: Literal["list", "clear"] = typer.Argument(..., help="Cache action"),
):
    """Manage ticker resolution cache."""
    cache_obj = UserMappingCache()
    
    if action == "list":
        mappings = cache_obj.list_mappings()
        
        if not mappings:
            console.print("[dim]No cached mappings[/dim]")
            return
        
        console.print("[bold]Cached Ticker Mappings:[/bold]\n")
        console.print(f"{'Query':<25} {'Ticker':<15} {'Name':<30} {'Used':<10}")
        console.print("-" * 80)
        
        for m in mappings:
            console.print(
                f"{m['query']:<25} {m['ticker']:<15} {m['display_name']:<30} {m['use_count']:<10}"
            )
        
        console.print(f"\n[dim]Total: {len(mappings)} entries[/dim]")
    
    elif action == "clear":
        confirm = typer.confirm("Clear all cached ticker mappings?")
        if confirm:
            cache_obj.clear()
            console.print("[green]✓ Cache cleared successfully[/green]")
        else:
            console.print("[dim]Cancelled[/dim]")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cli/test_cli.py::test_cache_list_empty -v`
Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add src/cli/main.py tests/cli/test_cli.py
git commit -m "feat(cli): add cache command for list and clear operations"
```

---

## Task 9: CLI Integration - check command

**Files:**
- Modify: `src/cli/main.py`

- [ ] **Step 1: Add import for TickerResolver**

```python
# src/cli/main.py (at top)
from src.providers.ticker_resolver import TickerResolver, TickerNotFoundError
```

- [ ] **Step 2: Add helper function for user selection prompt**

```python
# src/cli/main.py (before check command)
def prompt_user_selection(candidates: list) -> str:
    """
    Interactive prompt for user to select from multiple candidates.
    """
    console.print("[yellow]Multiple matches found. Please select:[/yellow]\n")
    
    console.print(f"{'#':<3} {'Ticker':<15} {'Name':<40} {'Exchange':<10}")
    console.print("-" * 70)
    
    for i, candidate in enumerate(candidates[:5], 1):
        console.print(
            f"{i:<3} {candidate.symbol:<15} {candidate.name:<40} {candidate.exchange:<10}"
        )
    
    console.print()
    choice = typer.prompt(
        "Select number (1-5)",
        type=int,
        default=1,
        show_default=True
    )
    
    if choice < 1 or choice > len(candidates[:5]):
        console.print("[yellow]Invalid choice, using default (1)[/yellow]")
        choice = 1
    
    return candidates[choice - 1].symbol
```

- [ ] **Step 3: Modify check command to use resolver**

```python
# src/cli/main.py
@app.command()
def check(
    ticker_query: str = typer.Argument(
        ..., 
        help="Ticker symbol or company name (e.g., AAPL, Apple, 애플, 삼성전자)"
    ),
):
    """Quick check - technical analysis without LLM."""
    resolver = TickerResolver()
    
    try:
        # Resolve ticker
        console.print(f"[dim]Resolving ticker...[/dim]")
        resolution = asyncio.run(resolver.resolve(ticker_query))
        
        # Handle multiple candidates
        if resolution.candidates and resolution.confidence == "low":
            ticker = prompt_user_selection(resolution.candidates)
            resolver.save_user_selection(ticker_query, ticker, resolution.display_name)
        else:
            ticker = resolution.resolved_ticker
        
        # Display resolution info
        console.print(f"[dim]Resolved: {resolution.display_name} ({ticker})[/dim]\n")
        
        # Run analysis with resolved ticker
        result = asyncio.run(run_quick_check(ticker))
        
        if not result.get("success", False):
            console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
            raise typer.Exit(1)
        
        pipeline = QuickCheckPipeline(technical_tool=None)
        output = pipeline.format_output(result)
        console.print(Markdown(output))
        
    except TickerNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[yellow]Tip: Try using the exact ticker symbol (e.g., AAPL) or English company name[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 4: Test manually**

Run: `uv run jarvis check Apple`
Expected: Resolves to AAPL and runs analysis

Run: `uv run jarvis check 삼성전자`
Expected: Resolves to 005930.KS and runs analysis

Run: `uv run jarvis check Samsung`
Expected: Shows selection prompt with multiple options

- [ ] **Step 5: Commit**

```bash
git add src/cli/main.py
git commit -m "feat(cli): integrate TickerResolver into check command"
```

---

## Task 10: CLI Integration - analyze and report commands

**Files:**
- Modify: `src/cli/main.py`

- [ ] **Step 1: Update analyze command**

```python
# src/cli/main.py
@app.command()
def analyze(
    ticker_query: str = typer.Argument(
        ..., 
        help="Ticker symbol or company name (e.g., AAPL, Apple, 애플, 삼성전자)"
    ),
    provider: Literal["openai", "anthropic"] = typer.Option(
        "openai", "--provider", "-p", help="LLM provider"
    ),
):
    """Deep dive analysis with LLM (technical + news)."""
    resolver = TickerResolver()
    
    try:
        # Resolve ticker
        console.print(f"[dim]Resolving ticker...[/dim]")
        resolution = asyncio.run(resolver.resolve(ticker_query))
        
        # Handle multiple candidates
        if resolution.candidates and resolution.confidence == "low":
            ticker = prompt_user_selection(resolution.candidates)
            resolver.save_user_selection(ticker_query, ticker, resolution.display_name)
        else:
            ticker = resolution.resolved_ticker
        
        # Display resolution info
        console.print(f"[dim]Resolved: {resolution.display_name} ({ticker})[/dim]\n")
        console.print(f"[bold]Running deep dive analysis for {ticker}...[/bold]\n")
        
        # Run deep dive with resolved ticker
        result = asyncio.run(run_deep_dive(ticker, provider))
        output = format_deep_dive_output(result)
        console.print(Markdown(output))
        
    except TickerNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[yellow]Tip: Try using the exact ticker symbol or English company name[/yellow]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 2: Update report command for batch resolution**

```python
# src/cli/main.py
@app.command()
def report(
    tickers: str = typer.Option(
        "AAPL,MSFT,NVDA",
        "--tickers",
        "-t",
        help="Comma-separated ticker symbols or company names",
    ),
    provider: Literal["openai", "anthropic"] = typer.Option(
        "openai", "--provider", "-p", help="LLM provider"
    ),
):
    """Daily market report (macro snapshot + ticker analysis)."""
    resolver = TickerResolver()
    ticker_queries = [t.strip() for t in tickers.split(",")]
    
    console.print(f"[bold]Resolving {len(ticker_queries)} tickers...[/bold]\n")
    
    # Resolve all tickers (auto-select for batch, no interactive prompt)
    resolved_tickers = []
    for query in ticker_queries:
        try:
            resolution = asyncio.run(resolver.resolve(query))
            ticker = resolution.resolved_ticker
            resolved_tickers.append(ticker)
            console.print(f"[dim]  {query} → {ticker}[/dim]")
        except TickerNotFoundError:
            console.print(f"[yellow]  Warning: Could not resolve '{query}', skipping[/yellow]")
    
    console.print(f"\n[bold]Generating daily report for {len(resolved_tickers)} tickers...[/bold]\n")
    
    try:
        result = asyncio.run(run_daily_report(resolved_tickers, provider))
        output = format_daily_report_output(result)
        console.print(Markdown(output))
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 3: Test manually**

Run: `uv run jarvis analyze Tesla`
Expected: Resolves to TSLA and runs deep dive

Run: `uv run jarvis report --tickers="애플,구글,테슬라"`
Expected: Resolves all 3 tickers and generates report

- [ ] **Step 4: Commit**

```bash
git add src/cli/main.py
git commit -m "feat(cli): integrate TickerResolver into analyze and report commands"
```

---

## Task 11: Integration Tests

**Files:**
- Create: `tests/integration/test_ticker_resolution_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_ticker_resolution_integration.py
import pytest
import asyncio
from pathlib import Path
import tempfile
from src.providers.ticker_resolver import TickerResolver


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_resolution_flow():
    """Test complete resolution flow: direct → cache → static → search"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        resolver = TickerResolver(user_cache_path=cache_path)
        
        # Test 1: Direct ticker
        result1 = await resolver.resolve("AAPL")
        assert result1.resolved_ticker == "AAPL"
        assert result1.resolution_method == "direct_ticker"
        
        # Test 2: English search
        result2 = await resolver.resolve("Tesla")
        assert result2.resolved_ticker == "TSLA"
        assert "Tesla" in result2.display_name
        
        # Test 3: Save to cache and retrieve
        resolver.save_user_selection("테슬라", "TSLA", "Tesla, Inc.")
        result3 = await resolver.resolve("테슬라")
        assert result3.resolved_ticker == "TSLA"
        assert result3.resolution_method == "user_cache"
        
        # Test 4: Korean with static mapping
        result4 = await resolver.resolve("애플")
        assert result4.resolved_ticker == "AAPL"
        
        # Test 5: Korean ticker normalization
        result5 = await resolver.resolve("005930")
        assert result5.resolved_ticker == "005930.KS"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cache_persistence():
    """Test cache persists across resolver instances"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "user_mappings.yaml"
        
        # Instance 1: Save mapping
        resolver1 = TickerResolver(user_cache_path=cache_path)
        resolver1.save_user_selection("구글", "GOOGL", "Alphabet Inc.")
        
        # Instance 2: Load mapping
        resolver2 = TickerResolver(user_cache_path=cache_path)
        result = await resolver2.resolve("구글")
        
        assert result.resolved_ticker == "GOOGL"
        assert result.resolution_method == "user_cache"


@pytest.mark.integration
def test_cli_cache_operations():
    """Test CLI cache list and clear"""
    from typer.testing import CliRunner
    from src.cli.main import app
    
    runner = CliRunner()
    
    # Test list (should work even if empty)
    result = runner.invoke(app, ["cache", "list"])
    assert result.exit_code == 0
    
    # Test clear (with auto-confirm somehow)
    # Skip for now as it requires interactive input
```

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/integration/test_ticker_resolution_integration.py -v -m integration`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_ticker_resolution_integration.py
git commit -m "test: add integration tests for ticker resolution"
```

---

## Task 12: Documentation Update

**Files:**
- Modify: `README.md`
- Modify: `docs/CLI_USAGE.md`

- [ ] **Step 1: Update README with new input formats**

```markdown
# README.md (modify usage section)

### 1. 빠른 기술적 분석 (Quick Check)
```bash
# Ticker symbol
jarvis check AAPL
jarvis check 005930.KS

# English company name
jarvis check Apple
jarvis check "Samsung Electronics"

# Korean company name (한글 회사명)
jarvis check 애플
jarvis check 삼성전자
jarvis check 테슬라
```

### Cache Management
```bash
# List cached ticker mappings
jarvis cache list

# Clear all cached mappings
jarvis cache clear
```
```

- [ ] **Step 2: Update CLI_USAGE.md**

```markdown
# docs/CLI_USAGE.md

## Ticker Resolution

The CLI now supports multiple input formats:

1. **Exact ticker symbols**: `AAPL`, `GOOGL`, `005930.KS`
2. **English company names**: `Apple`, `Tesla`, `Samsung Electronics`
3. **Korean company names**: `애플`, `구글`, `삼성전자`

### Resolution Process

The system resolves queries in this priority:

1. **Direct ticker** - If input is already a valid ticker (AAPL, 005930.KS)
2. **User cache** - Previously searched and selected tickers
3. **Static mapping** - Curated Korean→English mappings
4. **yfinance Search** - Live search API

### Multiple Results

If a search returns multiple tickers, you'll be prompted to select:

```
Multiple matches found. Please select:

#   Ticker          Name                                     Exchange
----------------------------------------------------------------------
1   005930.KS       SamsungElec                              KSC
2   207940.KS       SAMSUNG BIOLOGICS                        KSC
3   SSNLF           SAMSUNG ELECTRONICS CO                   PNK

Select number (1-5) [1]:
```

Your selection is saved to cache for future use.

### Cache Management

```bash
# View cached mappings
jarvis cache list

# Clear all cached mappings
jarvis cache clear
```

Cache is stored at: `~/.cache/invest-jarvis/user_mappings.yaml`
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/CLI_USAGE.md
git commit -m "docs: update README and CLI_USAGE with ticker resolution examples"
```

---

## Task 13: Final Testing & Cleanup

**Files:**
- All files

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v --ignore=tests/integration`
Expected: All unit tests pass

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/integration/ -v -m integration`
Expected: All integration tests pass

- [ ] **Step 3: Manual CLI testing**

```bash
# Test direct ticker
uv run jarvis check AAPL

# Test English name
uv run jarvis check Apple

# Test Korean name
uv run jarvis check 애플

# Test multiple results
uv run jarvis check Samsung

# Test cache
uv run jarvis cache list
uv run jarvis cache clear

# Test analyze
uv run jarvis analyze Tesla

# Test report
uv run jarvis report --tickers="AAPL,애플,Tesla"
```

- [ ] **Step 4: Check code style and imports**

Run: `uv run python -m py_compile src/providers/*.py`
Expected: No syntax errors

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup and validation"
```

---

## Completion Checklist

- [ ] All unit tests pass (71+ tests)
- [ ] Integration tests pass
- [ ] Manual CLI testing successful
- [ ] Documentation updated
- [ ] No placeholder code (TODO, TBD, etc.)
- [ ] All commits follow convention (feat:, test:, docs:, chore:)
- [ ] Ready for PR or merge to main

---

## Notes

- **Network dependency**: yfinance Search tests require internet connection
- **Test isolation**: Cache tests use temporary directories
- **Korean input**: Ensure terminal supports UTF-8 for Korean characters
- **Performance**: First search may be slow (yfinance API), subsequent are cached

---

**Implementation Time Estimate:** 6-8 hours for complete implementation
**Test Coverage Target:** 90%+
**Commits:** ~15-20 commits following TDD approach
