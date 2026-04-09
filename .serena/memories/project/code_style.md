# Code Style and Conventions

## Python Style
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Type hints**: Full type hints throughout (Python 3.12+), using `|` for unions instead of `Union`
- **Async**: Extensive use of async/await patterns
- **Docstrings**: Google-style docstrings with Args/Returns sections

## Patterns
- **Providers**: All providers are async classes with methods that fetch external data
- **Models**: Pydantic BaseModel for all data structures with type hints
- **Error handling**: Try/except blocks to gracefully handle API failures
- **No hardcoding**: Use type hints for flexibility

## Example (from providers):
```python
async def get_themes(self, top_n: int = 10) -> list[dict]:
    """Get top themes with their stocks.
    
    Returns:
        list[dict]: List of themes with keys (name, change_rate, theme_id, stocks)
    """
```
