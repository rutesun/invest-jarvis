---
description: Daily market report with macro indicators
skill_type: user-invocable
---

# invest-report

Generate daily market report with macro snapshot and top movers.

**Usage:** `/invest-report` or `/invest-report AAPL,MSFT,NVDA`

**What it does:**
- Runs `jarvis report` command
- Macro indicators (VIX, Fear & Greed, WTI, Yields, DXY)
- Technical analysis for specified tickers
- Market summary

**Requires:** OPENAI_API_KEY or ANTHROPIC_API_KEY

**Examples:**
- `/invest-report` - Default tickers (AAPL, MSFT, NVDA)
- `/invest-report AAPL,TSLA,GOOGL` - Custom tickers

---

## Implementation

When invoked:

1. Extract tickers from user input (optional)
2. Check API key availability
3. Run: `jarvis report --tickers=<tickers>`
4. Display formatted output

```python
import subprocess
import os
import sys

tickers = "{{TICKERS}}" or "AAPL,MSFT,NVDA"

if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
    print("Error: OPENAI_API_KEY or ANTHROPIC_API_KEY required")
    sys.exit(1)

result = subprocess.run(
    ["jarvis", "report", f"--tickers={tickers}"],
    capture_output=True,
    text=True,
)

if result.returncode == 0:
    print(result.stdout)
else:
    print(f"Error: {result.stderr}")
    sys.exit(1)
```
