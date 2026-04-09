# Ticker Resolution System Design

**Date:** 2026-04-09  
**Status:** Approved  
**Author:** Claude Code with user collaboration

## Overview

Enable users to search stocks using company names (English and Korean) in addition to ticker symbols. The system should intelligently resolve user input to valid ticker symbols using static mappings, learned user preferences, and yfinance Search API.

## Requirements

### Functional Requirements

1. **Input Flexibility**: Accept multiple input formats
   - Exact ticker symbols (AAPL, GOOGL, 005930.KS)
   - English company names (Apple, Google, Samsung Electronics)
   - Korean company names (애플, 구글, 삼성전자)
   - Partial matches should fallback to search

2. **Smart Resolution**: Multi-stage resolution process
   - Direct ticker validation (fastest)
   - User cache lookup (learned preferences)
   - Static mapping (curated list)
   - yfinance Search API (fallback)

3. **Multi-Result Handling**: When search returns multiple candidates
   - If 1 result: auto-select with high confidence
   - If 2+ results: prompt user to select from list
   - Save user selection to cache for future use

4. **User Cache**: Learn from user selections
   - Save query → ticker mappings after user selection
   - Track usage statistics (count, last_used)
   - Auto-cleanup old entries (6 months unused)
   - Provide cache management commands

5. **Error Handling**: Clear messages and recovery
   - Invalid ticker: suggest alternatives
   - No search results: guide user to use exact ticker
   - API failures: fallback gracefully

### Non-Functional Requirements

- **Performance**: Resolution < 2s (including network)
- **Reliability**: Graceful degradation if yfinance unavailable
- **Usability**: Clear feedback on resolution process
- **Maintainability**: Separation of concerns, testable components

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────┐
│              CLI Commands                    │
│  (check, analyze, report, cache)            │
└─────────────┬───────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────┐
│          TickerResolver                      │
│  - resolve(query) → TickerResolution        │
│  - Resolution priority logic                 │
└─────┬───────────────────────────────────────┘
      │
      ├──► Direct Ticker Detection
      │    (regex patterns)
      │
      ├──► UserMappingCache
      │    (~/.cache/invest-jarvis/user_mappings.yaml)
      │
      ├──► Static Mapping
      │    (config/ticker_names.yaml)
      │
      └──► yfinance Search API
           (fallback)
```

### Core Components

#### 1. TickerResolver (`src/providers/ticker_resolver.py`)

Central resolution logic with priority-based strategy.

```python
class TickerResolver:
    def __init__(
        self, 
        static_mapping_path: str = "config/ticker_names.yaml",
        user_cache_path: Optional[Path] = None
    ):
        self.static_mapping = self._load_yaml(static_mapping_path)
        self.user_cache = UserMappingCache(user_cache_path)
        self._search_cache = {}  # In-memory cache for yfinance results
    
    async def resolve(self, query: str) -> TickerResolution:
        """
        Resolve user query to ticker symbol.
        
        Priority:
        1. Direct ticker detection (AAPL, 005930.KS)
        2. User cache lookup
        3. Static mapping (Korean → English)
        4. yfinance Search API
        """
    
    def save_user_selection(self, query: str, ticker: str, display_name: str):
        """Save user-selected ticker to cache"""
```

#### 2. UserMappingCache (`src/providers/ticker_cache.py`)

Manages user-learned ticker mappings.

```python
class UserMappingCache:
    def __init__(self, cache_path: Path):
        self.cache_path = cache_path or self._default_cache_path()
        self.max_entries = 200
        self.expiry_days = 180  # 6 months
    
    def get(self, query: str) -> Optional[CachedMapping]:
        """Get cached mapping if exists and not expired"""
    
    def save(self, query: str, ticker: str, display_name: str):
        """Save new mapping or update existing"""
    
    def update_usage(self, query: str):
        """Update last_used timestamp and increment use_count"""
    
    def cleanup_old_entries(self):
        """Remove entries unused for 6+ months or enforce LRU limit"""
    
    def list_mappings(self) -> list[CachedMapping]:
        """Return all cached mappings sorted by usage"""
    
    def clear(self):
        """Clear all cached mappings"""
```

#### 3. Data Models (`src/providers/ticker_models.py`)

```python
from pydantic import BaseModel
from typing import Literal
from datetime import datetime

class CandidateTicker(BaseModel):
    symbol: str
    name: str
    exchange: str
    score: float
    quote_type: str  # "EQUITY", "ETF", "INDEX"

class TickerResolution(BaseModel):
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

class CachedMapping(BaseModel):
    ticker: str
    display_name: str
    created_at: datetime
    last_used: datetime
    use_count: int
```

## Resolution Strategy

### Step-by-Step Flow

```
User Input: "삼성전자"
    ↓
[1] Direct Ticker Check
    Pattern match: ^\d{6}$, ^[A-Z]{1,5}$, ^\d{6}\.KS$
    ❌ Not a direct ticker
    ↓
[2] User Cache Lookup
    Check ~/.cache/invest-jarvis/user_mappings.yaml
    ✓ Found: "삼성전자" → "005930.KS" (used 3 times)
    ↓
[Return] TickerResolution(
    resolved_ticker="005930.KS",
    display_name="SamsungElec",
    confidence="high",
    resolution_method="user_cache"
)
```

```
User Input: "Apple"
    ↓
[1] Direct Ticker Check ❌
    ↓
[2] User Cache Lookup ❌
    ↓
[3] Static Mapping Lookup
    Check config/ticker_names.yaml
    ❌ "Apple" not in Korean mapping
    ↓
[4] yfinance Search API
    yf.Search("Apple") → 3 results
    [0] AAPL (score: 35427)
    [1] APLE (score: 20020)
    [2] APC.DE (score: 20006)
    ↓
    Single dominant result (score gap > 50%)
    ✓ Auto-select AAPL
    ↓
[Save] user_cache["Apple"] = "AAPL"
    ↓
[Return] TickerResolution(
    resolved_ticker="AAPL",
    display_name="Apple Inc.",
    confidence="high",
    resolution_method="yfinance_search_single"
)
```

```
User Input: "Samsung"
    ↓
[1-3] Direct, Cache, Static ❌
    ↓
[4] yfinance Search API
    yf.Search("Samsung") → 5 results
    [0] 005930.KS (SamsungElec)
    [1] 207940.KS (SAMSUNG BIOLOGICS)
    [2] XSDG.F (SAMSUNG SDI)
    [3] SSNLF (SAMSUNG ELECTRONICS)
    [4] SMSN.IL (SAMSUNG ELECTRONICS)
    ↓
    Multiple relevant results
    ↓
[Prompt] User to select from list
    User selects: [1] 005930.KS
    ↓
[Save] user_cache["Samsung"] = "005930.KS"
    ↓
[Return] TickerResolution(
    resolved_ticker="005930.KS",
    candidates=[...],
    confidence="medium",
    resolution_method="yfinance_search_multiple"
)
```

### Direct Ticker Detection

```python
def is_direct_ticker(query: str) -> bool:
    """Check if input is already a valid ticker symbol"""
    patterns = [
        r'^[A-Z]{1,5}$',           # US stocks: AAPL, GOOGL
        r'^\d{6}\.KS$',            # Korean stocks: 005930.KS
        r'^\d{6}\.KQ$',            # KOSDAQ: 123456.KQ
    ]
    return any(re.match(p, query) for p in patterns)

def normalize_korean_ticker(query: str) -> str:
    """Convert 6-digit code to .KS format"""
    if re.match(r'^\d{6}$', query):
        return f"{query}.KS"
    return query
```

### Static Mapping Lookup

```python
def lookup_static_mapping(self, query: str) -> Optional[str]:
    """
    Convert Korean company name to English via static mapping.
    Returns English name if found, None otherwise.
    """
    if not contains_korean(query):
        return None
    
    normalized_query = query.strip().lower()
    return self.static_mapping.get(normalized_query)
```

### yfinance Search Integration

```python
async def search_yfinance(self, query: str) -> list[CandidateTicker]:
    """
    Search tickers using yfinance Search API.
    Returns sorted list of candidates by relevance score.
    """
    # Check in-memory cache (60s TTL)
    cache_key = (query, int(time.time()) // 60)
    if cache_key in self._search_cache:
        return self._search_cache[cache_key]
    
    try:
        search = yf.Search(query)
        candidates = [
            CandidateTicker(
                symbol=q['symbol'],
                name=q.get('shortname', 'N/A'),
                exchange=q.get('exchange', 'N/A'),
                score=q.get('score', 0),
                quote_type=q.get('quoteType', 'EQUITY')
            )
            for q in search.quotes or []
        ]
        
        # Sort by score descending
        candidates.sort(key=lambda x: x.score, reverse=True)
        
        # Cache result
        self._search_cache[cache_key] = candidates
        
        return candidates
    except Exception as e:
        raise TickerResolutionError(f"Search failed: {e}")
```

### Multi-Result Selection Logic

```python
def determine_confidence(self, candidates: list[CandidateTicker]) -> tuple[str, Literal["high", "medium", "low"]]:
    """
    Determine if auto-selection is safe or user prompt needed.
    
    Returns: (selected_ticker, confidence_level)
    """
    if not candidates:
        raise TickerNotFoundError("No candidates found")
    
    if len(candidates) == 1:
        return candidates[0].symbol, "high"
    
    # Check score gap between top 2 results
    top_score = candidates[0].score
    second_score = candidates[1].score if len(candidates) > 1 else 0
    
    score_gap_pct = (top_score - second_score) / top_score if top_score > 0 else 0
    
    if score_gap_pct > 0.5:  # Top result 50%+ higher score
        return candidates[0].symbol, "high"
    
    # Ambiguous: need user input
    return candidates[0].symbol, "low"  # Default to top, but low confidence
```

## User Cache System

### File Structure

```
~/.cache/invest-jarvis/
├── user_mappings.yaml
└── (future: search_history.json)
```

### user_mappings.yaml Format

```yaml
version: 1
last_cleanup: "2026-04-09T10:00:00"
mappings:
  삼성전자:
    ticker: "005930.KS"
    display_name: "SamsungElec"
    created_at: "2026-04-01T15:30:00"
    last_used: "2026-04-09T14:00:00"
    use_count: 5
  
  Apple:
    ticker: "AAPL"
    display_name: "Apple Inc."
    created_at: "2026-04-05T09:20:00"
    last_used: "2026-04-09T11:30:00"
    use_count: 2
  
  Samsung:
    ticker: "005930.KS"
    display_name: "SamsungElec"
    created_at: "2026-04-08T16:45:00"
    last_used: "2026-04-08T16:45:00"
    use_count: 1
```

### Cache Management

**Auto-cleanup triggers:**
- On application start (if last_cleanup > 7 days ago)
- When cache size > max_entries (LRU eviction)
- Manual: `jarvis cache clear`

**Cleanup logic:**
```python
def cleanup_old_entries(self):
    """Remove stale entries"""
    now = datetime.now()
    cutoff = now - timedelta(days=self.expiry_days)
    
    # Remove entries not used in 6 months
    self.mappings = {
        k: v for k, v in self.mappings.items()
        if v.last_used > cutoff
    }
    
    # Enforce LRU limit
    if len(self.mappings) > self.max_entries:
        sorted_entries = sorted(
            self.mappings.items(),
            key=lambda x: x[1].last_used,
            reverse=True
        )
        self.mappings = dict(sorted_entries[:self.max_entries])
    
    self._save()
```

### Cache CLI Commands

```bash
# List all cached mappings
jarvis cache list

# Clear all cached mappings
jarvis cache clear

# Show cache statistics
jarvis cache stats  # (future)
```

## Static Mapping Configuration

### config/ticker_names.yaml

Initial seed with top 50-100 frequently searched stocks.

```yaml
# Korean company name → English company name
korean_to_english:
  # US Tech Stocks
  애플: Apple
  구글: Google
  알파벳: Alphabet
  테슬라: Tesla
  마이크로소프트: Microsoft
  아마존: Amazon
  메타: Meta
  엔비디아: NVIDIA
  넷플릭스: Netflix
  아마존: Amazon
  
  # Korean Stocks
  삼성전자: Samsung Electronics
  SK하이닉스: SK Hynix
  현대차: Hyundai Motor
  기아: Kia
  셀트리온: Celltrion
  삼성바이오로직스: Samsung Biologics
  카카오: Kakao
  네이버: NAVER
  LG에너지솔루션: LG Energy Solution
  LG화학: LG Chem
  POSCO홀딩스: POSCO Holdings
  
  # Common aliases
  구글: Alphabet
  페이스북: Meta
  삼성: Samsung Electronics
  현대: Hyundai Motor
```

## CLI Integration

### Modified Commands

#### check command

```python
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

#### analyze command

Similar changes to `check`, with ticker resolution before deep dive.

#### report command

```python
@app.command()
def report(
    tickers: str = typer.Option(
        "AAPL,MSFT,NVDA",
        "--tickers",
        "-t",
        help="Comma-separated ticker symbols or company names",
    ),
    ...
):
    """Daily market report."""
    resolver = TickerResolver()
    ticker_queries = [t.strip() for t in tickers.split(",")]
    
    # Resolve all tickers
    resolved_tickers = []
    for query in ticker_queries:
        try:
            resolution = asyncio.run(resolver.resolve(query))
            # Auto-select for batch operations (no interactive prompt)
            resolved_tickers.append(resolution.resolved_ticker)
        except TickerNotFoundError:
            console.print(f"[yellow]Warning: Could not resolve '{query}', skipping[/yellow]")
    
    # Run report with resolved tickers
    ...
```

#### cache command (new)

```python
@app.command()
def cache(
    action: Literal["list", "clear"] = typer.Argument(..., help="Cache action"),
):
    """Manage ticker resolution cache."""
    cache_path = Path.home() / ".cache/invest-jarvis/user_mappings.yaml"
    cache = UserMappingCache(cache_path)
    
    if action == "list":
        mappings = cache.list_mappings()
        
        if not mappings:
            console.print("[dim]No cached mappings[/dim]")
            return
        
        console.print("[bold]Cached Ticker Mappings:[/bold]\n")
        console.print(f"{'Query':<25} {'Ticker':<15} {'Name':<30} {'Used':<10}")
        console.print("-" * 80)
        
        for m in mappings:
            console.print(
                f"{m.query:<25} {m.ticker:<15} {m.display_name:<30} {m.use_count:<10}"
            )
        
        console.print(f"\n[dim]Total: {len(mappings)} entries[/dim]")
    
    elif action == "clear":
        confirm = typer.confirm("Clear all cached ticker mappings?")
        if confirm:
            cache.clear()
            console.print("[green]✓ Cache cleared successfully[/green]")
        else:
            console.print("[dim]Cancelled[/dim]")
```

### User Selection Prompt

```python
def prompt_user_selection(candidates: list[CandidateTicker]) -> str:
    """
    Interactive prompt for user to select from multiple candidates.
    Uses rich formatting for better UX.
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

## Error Handling

### Custom Exceptions

```python
class TickerResolutionError(Exception):
    """Base exception for ticker resolution"""
    pass

class TickerNotFoundError(TickerResolutionError):
    """No ticker found for query"""
    pass

class InvalidTickerError(TickerResolutionError):
    """Ticker format is invalid"""
    pass

class SearchAPIError(TickerResolutionError):
    """yfinance Search API error"""
    pass
```

### Error Messages

```python
# No results found
try:
    resolution = await resolver.resolve("InvalidCompany123")
except TickerNotFoundError:
    console.print("[red]Could not find ticker for 'InvalidCompany123'[/red]")
    console.print("[yellow]Tip: Try using the exact ticker symbol (e.g., AAPL) or English company name[/yellow]")

# yfinance API down
try:
    resolution = await resolver.resolve("Apple")
except SearchAPIError:
    console.print("[red]Search service temporarily unavailable[/red]")
    console.print("[yellow]Please use exact ticker symbol (e.g., AAPL, 005930.KS)[/yellow]")

# Invalid format
try:
    validate_query("rm -rf /")  # Malicious input
except InvalidTickerError:
    console.print("[red]Invalid query format[/red]")
```

### Input Validation

```python
def validate_query(query: str) -> str:
    """Validate and sanitize user input"""
    if not query or len(query) > 50:
        raise InvalidTickerError("Query must be 1-50 characters")
    
    # Allow: alphanumeric, spaces, hyphens, Korean characters
    allowed_pattern = r'^[A-Za-z0-9가-힣\s\-\.]+$'
    if not re.match(allowed_pattern, query):
        raise InvalidTickerError("Query contains invalid characters")
    
    return query.strip()
```

## Testing Strategy

### Unit Tests

**test_ticker_resolver.py**

```python
@pytest.mark.asyncio
async def test_direct_ticker_us():
    """Test US ticker direct detection"""
    resolver = TickerResolver()
    result = await resolver.resolve("AAPL")
    assert result.resolved_ticker == "AAPL"
    assert result.resolution_method == "direct_ticker"
    assert result.confidence == "high"

@pytest.mark.asyncio
async def test_direct_ticker_korean():
    """Test Korean ticker with .KS suffix"""
    resolver = TickerResolver()
    result = await resolver.resolve("005930.KS")
    assert result.resolved_ticker == "005930.KS"
    assert result.resolution_method == "direct_ticker"

@pytest.mark.asyncio
async def test_korean_ticker_normalization():
    """Test 6-digit code auto-adds .KS"""
    resolver = TickerResolver()
    result = await resolver.resolve("005930")
    assert result.resolved_ticker == "005930.KS"

@pytest.mark.asyncio
async def test_static_mapping_korean():
    """Test Korean name via static mapping"""
    resolver = TickerResolver()
    result = await resolver.resolve("삼성전자")
    assert "005930" in result.resolved_ticker or "Samsung" in result.display_name

@pytest.mark.asyncio
async def test_yfinance_search_english():
    """Test English company name search"""
    resolver = TickerResolver()
    result = await resolver.resolve("Apple")
    assert result.resolved_ticker == "AAPL"

@pytest.mark.asyncio
async def test_multiple_candidates():
    """Test multiple search results"""
    resolver = TickerResolver()
    result = await resolver.resolve("Samsung")
    assert len(result.candidates) > 1
    assert result.confidence == "low"

@pytest.mark.asyncio
async def test_not_found():
    """Test invalid query raises error"""
    resolver = TickerResolver()
    with pytest.raises(TickerNotFoundError):
        await resolver.resolve("InvalidCompanyXYZ123")

@pytest.mark.asyncio
async def test_cache_hit():
    """Test user cache lookup"""
    cache = UserMappingCache()
    cache.save("테슬라", "TSLA", "Tesla, Inc.")
    
    resolver = TickerResolver()
    result = await resolver.resolve("테슬라")
    assert result.resolved_ticker == "TSLA"
    assert result.resolution_method == "user_cache"
```

**test_ticker_cache.py**

```python
def test_cache_save_and_get():
    cache = UserMappingCache()
    cache.save("애플", "AAPL", "Apple Inc.")
    
    mapping = cache.get("애플")
    assert mapping is not None
    assert mapping.ticker == "AAPL"
    assert mapping.use_count == 1

def test_cache_update_usage():
    cache = UserMappingCache()
    cache.save("구글", "GOOGL", "Alphabet Inc.")
    
    initial_count = cache.get("구글").use_count
    cache.update_usage("구글")
    
    updated = cache.get("구글")
    assert updated.use_count == initial_count + 1

def test_cache_cleanup_old():
    cache = UserMappingCache(expiry_days=1)
    
    # Create old entry
    old_time = datetime.now() - timedelta(days=2)
    cache.mappings["old"] = CachedMapping(
        ticker="OLD",
        display_name="Old Stock",
        created_at=old_time,
        last_used=old_time,
        use_count=1
    )
    
    cache.cleanup_old_entries()
    assert "old" not in cache.mappings

def test_cache_lru_limit():
    cache = UserMappingCache(max_entries=3)
    
    for i in range(5):
        cache.save(f"query{i}", f"TICK{i}", f"Stock {i}")
    
    assert len(cache.list_mappings()) == 3
```

### Integration Tests

```bash
# Test real CLI commands
jarvis check AAPL
jarvis check Apple
jarvis check 애플
jarvis check 삼성전자
jarvis check Samsung  # Should prompt for selection

jarvis cache list
jarvis cache clear

# Test error cases
jarvis check InvalidCompany123  # Should show error
jarvis check ""  # Should show validation error
```

### Performance Tests

```python
@pytest.mark.benchmark
async def test_resolution_performance():
    resolver = TickerResolver()
    
    start = time.time()
    await resolver.resolve("AAPL")  # Direct ticker
    direct_time = time.time() - start
    assert direct_time < 0.1  # < 100ms
    
    start = time.time()
    await resolver.resolve("애플")  # Cached
    cache_time = time.time() - start
    assert cache_time < 0.2  # < 200ms
    
    start = time.time()
    await resolver.resolve("Tesla")  # Search
    search_time = time.time() - start
    assert search_time < 2.0  # < 2s
```

## Configuration

### config.yaml additions

```yaml
ticker_resolution:
  static_mapping_file: config/ticker_names.yaml
  user_cache_path: ~/.cache/invest-jarvis/user_mappings.yaml
  cache_max_entries: 200
  cache_expiry_days: 180
  search_timeout: 10  # seconds
  search_cache_ttl: 60  # seconds
```

## Implementation Plan

### Phase 1: Core Resolver (Week 1, Days 1-3)

**Files to create:**
- `src/providers/ticker_models.py` (data models)
- `src/providers/ticker_resolver.py` (core logic)

**Tasks:**
1. Create Pydantic models (TickerResolution, CandidateTicker)
2. Implement direct ticker detection
3. Implement static mapping lookup
4. Implement yfinance Search integration
5. Implement resolution priority logic
6. Write unit tests for resolver

**Acceptance criteria:**
- All resolution methods work independently
- Tests pass with 90%+ coverage
- Performance targets met

### Phase 2: User Cache (Week 1, Days 4-5)

**Files to create:**
- `src/providers/ticker_cache.py`

**Tasks:**
1. Implement UserMappingCache class
2. YAML save/load with proper error handling
3. Cleanup logic (expiry, LRU)
4. Cache management functions
5. Write unit tests for cache

**Acceptance criteria:**
- Cache persists across runs
- Cleanup works correctly
- Thread-safe operations

### Phase 3: CLI Integration (Week 2, Days 1-3)

**Files to modify:**
- `src/cli/main.py`

**Tasks:**
1. Add `cache` command (list, clear)
2. Update `check` command with resolution
3. Update `analyze` command with resolution
4. Update `report` command (batch resolution)
5. Implement user selection prompt UI
6. Add error handling and messages

**Acceptance criteria:**
- All commands work with company names
- User selection prompt is clear and works
- Error messages are helpful

### Phase 4: Skills Integration (Week 2, Days 4-5)

**Files to modify:**
- `skills/invest-check.md`
- `skills/invest-analyze.md`

**Tasks:**
1. Update skill help text
2. Test skills with company names
3. Ensure resolution works in skill context

### Phase 5: Documentation & Polish (Week 2, Day 5)

**Files to modify:**
- `README.md`
- `docs/CLI_USAGE.md`
- `config/ticker_names.yaml` (populate with 50+ entries)

**Tasks:**
1. Update README with examples
2. Add CLI usage documentation
3. Populate static mapping with common stocks
4. Performance optimization (if needed)
5. Final integration testing

### Testing Checkpoints

- After Phase 1: Unit tests pass
- After Phase 2: Cache tests pass, manual testing
- After Phase 3: CLI integration tests pass
- After Phase 4: Skills work correctly
- After Phase 5: Full end-to-end testing

## Migration & Rollout

### Backwards Compatibility

**Existing behavior preserved:**
- Direct ticker input (AAPL, 005930.KS) works exactly as before
- No breaking changes to CLI API

**New capabilities:**
- Company name input now supported
- User cache is opt-in (auto-creates on first use)

### Rollout Strategy

1. **Initial static mapping**: Add 50-100 common stocks to `config/ticker_names.yaml`
2. **User cache**: Creates automatically on first multi-result selection
3. **Documentation**: Update README with examples of new input formats
4. **Announcement**: Release notes explaining new search capability

### Risk Mitigation

**Risk: yfinance Search API unavailable**
- Mitigation: Graceful fallback, clear error message
- User can still use exact tickers

**Risk: Incorrect auto-selection**
- Mitigation: Display resolved ticker before analysis
- User can Ctrl+C and retry with exact ticker

**Risk: Cache corruption**
- Mitigation: Validate YAML on load, recreate if invalid
- User can always `jarvis cache clear`

## Future Enhancements (Out of Scope)

- **Fuzzy matching**: Handle typos (e.g., "Appl" → "Apple")
- **Multi-language**: Japanese, Chinese company names
- **Search history**: Track recent searches
- **Autocomplete**: CLI tab-completion for company names
- **Offline mode**: Embedded database of common tickers
- **Naver Finance integration**: Native Korean stock search
- **Popularity ranking**: Boost frequently searched stocks

## File Summary

### New Files
- `src/providers/ticker_models.py` (~80 lines)
- `src/providers/ticker_resolver.py` (~250 lines)
- `src/providers/ticker_cache.py` (~150 lines)
- `config/ticker_names.yaml` (~100 lines, data)
- `tests/providers/test_ticker_resolver.py` (~300 lines)
- `tests/providers/test_ticker_cache.py` (~150 lines)

### Modified Files
- `src/cli/main.py` (~100 lines changed)
- `skills/invest-check.md` (~10 lines)
- `skills/invest-analyze.md` (~10 lines)
- `README.md` (~50 lines added)
- `docs/CLI_USAGE.md` (~30 lines added)

### Total Effort
- **New code**: ~600 lines
- **Modified code**: ~200 lines
- **Test code**: ~450 lines
- **Documentation**: ~90 lines
- **Estimated time**: 2 weeks (1 developer)

---

**End of Design Document**
