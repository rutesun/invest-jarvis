---
description: Quick technical analysis check (lightweight CLI wrapper)
skill_type: user-invocable
---

# invest-check

Quick technical analysis for a stock ticker.

**Usage:** `/invest-check AAPL`

**What it does:**
- Runs `jarvis check <ticker>` command
- Shows price, indicators, trend analysis
- No LLM, fast response

**Examples:**
- `/invest-check AAPL` - Apple quick check
- `/invest-check MSFT` - Microsoft quick check
- `/invest-check 005930` - Samsung Electronics (KR)

---

## Implementation

When invoked:

1. Extract ticker from user input
2. Run: `jarvis check <ticker>`
3. Display formatted output

```python
import subprocess
import sys

# Get ticker from args
ticker = "{{TICKER}}"

# Run command
result = subprocess.run(
    ["jarvis", "check", ticker],
    capture_output=True,
    text=True,
)

# Display output
if result.returncode == 0:
    print(result.stdout)
else:
    print(f"Error: {result.stderr}")
    sys.exit(1)
```
