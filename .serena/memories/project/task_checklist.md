# Task 5: UniverseBuilder Implementation Checklist

## Objective
Create UniverseBuilder class to collect stock candidates from multiple data sources (KR+US markets).

## Files to Create
- `src/tools/screener/universe.py` - Implementation
- `tests/tools/screener/test_universe.py` - Tests

## Implementation Steps
- [x] Step 1: Write failing test (test_universe.py)
- [ ] Step 2: Run test to verify it fails
- [ ] Step 3: Write implementation (universe.py)
- [ ] Step 4: Run test to verify it passes
- [ ] Step 5: Commit changes

## Key Methods
- `__init__()` - Accept providers
- `build(market="all")` - Build universe for kr/us/all
- `_build_kr()` - Korean market sources: themes, volume, rise, KIS rankings
- `_build_us()` - US market sources: KIS up/down, KIS volume
- `_merge()` - Merge stocks, accumulating sources

## Korean Sources
1. Naver themes (top 10)
2. Naver volume ranking (top 30)
3. Naver rise ranking (top 30)
4. KIS investor ranking (foreign + institution, top 30 each)

## US Sources
1. KIS rise ranking (NAS + NYS, top 30 each)
2. KIS volume ranking (NAS + NYS, top 30 each)

## Error Handling
- Use try/except to continue if any source fails
- Return accumulated universe even if some sources fail
