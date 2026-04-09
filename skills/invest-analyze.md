---
description: Deep dive analysis with LLM (technical + news)
skill_type: user-invocable
---

# invest-analyze

Deep analysis combining technical indicators and news sentiment.

**Usage:** `/invest-analyze AAPL`

**What it does:**
- Runs `jarvis analyze <ticker>` command
- Technical analysis with LLM interpretation
- News sentiment analysis
- Actionable recommendations

**Requires:** OPENAI_API_KEY or ANTHROPIC_API_KEY

**Examples:**
- `/invest-analyze AAPL` - Apple deep dive
- `/invest-analyze TSLA` - Tesla analysis
- `/invest-analyze NVDA` - NVIDIA analysis

---

## Implementation

When invoked:

1. Extract ticker from user input
2. Check API key availability
3. Run: `jarvis analyze <ticker>`
4. Display formatted output with sections:
   - Technical Summary
   - News Analysis
   - Recommendation

```python
import subprocess
import os
import sys

ticker = "{{TICKER}}"

# Check API key
if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
    print("Error: OPENAI_API_KEY or ANTHROPIC_API_KEY required")
    sys.exit(1)

# Run command
result = subprocess.run(
    ["jarvis", "analyze", ticker],
    capture_output=True,
    text=True,
)

if result.returncode == 0:
    print(result.stdout)
else:
    print(f"Error: {result.stderr}")
    sys.exit(1)
```
