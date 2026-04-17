# LLM Model Evaluation Report: Complex Map Prompt

## 📊 Evaluation Summary
| Model | Granularity | Data Integrity | Insight | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **gpt-5.4-nano** | ★★★★★ | ★★★★★ | ★★★★☆ | **Primary Choice (T0.1)** |
| **gpt-5-mini** | ★★★★☆ | ★★★★☆ | ★★★★☆ | Secondary Choice |
| **gpt-5-nano** | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ | Not Recommended |

## 🔍 Detailed Findings

### 1. gpt-5.4-nano (The Winner)
- **Best-in-class Decoupling**: Successfully split multi-themed messages into 10+ distinct investment issues without lumping unrelated data.
- **Superior Precision**: Preserved all ticker prices and percentage changes (e.g., Ranix, OCI Holdings) even in dense list formats.
- **Consistent Structure**: Followed the P/Q/C impact analysis framework most effectively in the structured output fields.
- **Temperature Recommendation**: **0.1** is ideal. 0.0 is perfect for data but 0.1 adds better "Investment Narratives" to theme names as requested.

### 2. gpt-5-mini
- **High Semantic Clustering**: Tends to group issues into larger buckets. Good for "big picture" but loses some granularity required for per-ticker analysis.
- **Instruction Followership**: Most literal in following "Takeaway at the end of summary" prompt.

### 3. gpt-5-nano
- **Significant Data Loss**: Dropped several mid-to-small cap stock events and many secondary numerical data points. Too "lossy" for financial signal processing.

## 💡 Configuration Recommendation
Based on the benchmarks, we should update the pipeline to use:
- **Provider**: OpenAI
- **Model**: `gpt-5.4-nano`
- **Temperature**: `0.1` (or `0.0` for maximum extraction accuracy)
