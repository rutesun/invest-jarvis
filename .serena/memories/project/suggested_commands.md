# Development Commands

## Testing
```bash
uv run pytest tests/ -v                    # Run all tests
uv run pytest tests/tools/screener/ -v     # Run screener tests
uv run pytest -k test_universe -v          # Run specific test
uv run pytest --cov=src tests/             # With coverage
```

## Running
```bash
jarvis --help                              # Show CLI help
```

## Git
```bash
git status                                 # Check status
git add .                                  # Stage changes
git commit -m "message"                    # Commit
git log --oneline -10                      # Recent commits
```

## Project Structure
```
src/tools/screener/
  - models.py (UniverseStock, ScreenerEvidence)
  - scoring.py (5-factor scoring)
  - universe.py (UniverseBuilder - Task 5)
  - pipeline.py (ScreenerPipeline - Task 7)

tests/tools/screener/
  - test_models.py
  - test_scoring.py
  - test_universe.py (Task 5)
```
