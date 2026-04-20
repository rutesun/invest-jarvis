# Map Keywords Field Analysis

**Date**: 2026-04-20  
**Branch**: feat/source-tracking-and-keywords  
**Status**: Analysis Complete, Awaiting Decision

## Current Usage

Map stage generates `keywords` field for each `MappedIssue`, but investigation shows:

### Only Used Once
**Location**: `src/pipelines/daily_report/stages/reduce_stage.py:157`

```python
issues_text = "\n\n".join([
    f"**{issue.title}**\n{issue.summary}\n"
    f"키워드: {', '.join(issue.keywords)}\n"  # ← ONLY usage
    f"감성: {issue.sentiment}"
    for issue in issues
])
```

Map keywords are shown to Reduce LLM as context hint, but:
- Not used for filtering
- Not used for grouping
- Not used for search (Phase 2 will use **Reduce keywords**)
- Not returned in final report

## Quality Comparison

### Example 1: 매크로 테마

**Map keywords** (issue-level, 6개):
```
호르무즈 해협, 미-이란 협상, 유가 급락, 금리 인하 기대, 달러-원 환율, WTI 유가
```

**Reduce keywords** (theme-level, 10개):
```
호르무즈 해협, 미-이란 협상, 유가 변동성, WTI 유가, 금리 인하, 
달러-원 환율, 미국채 금리, 지정학적 리스크, 에너지 가격, 거시경제
```

### Example 2: 반도체 테마

**Map keywords** (5개):
```
메모리 공급 부족, 5년 장기계약, SK하이닉스 SOCAMM2, TSMC 1.4nm, UMC 웨이퍼 가격 인상
```

**Reduce keywords** (10개):
```
AI 메모리, DRAM 부족, 5년 장기계약, SK하이닉스, SOCAMM2, TSMC 1.4nm, 
메모리 가격, 웨이퍼, AI 데이터센터, 반도체 공급망
```

### Observation

Reduce keywords are consistently:
- ✅ More comprehensive (10 vs 5-6)
- ✅ More strategic/conceptual ("지정학적 리스크", "반도체 공급망")
- ✅ Better for theme-level search (spans multiple issues)

## Historical Context

### Original Design (Phase 1)
Map prompt says keywords are "웹 검색용" (line 200, 222 in prompts.py):
```
"keywords는 최신 데이터 검증을 위한 웹 검색 쿼리로 사용됩니다."
```

But this was **never implemented**. Map keywords ended up only being used as Reduce LLM hint.

### Future Plan (Phase 2)
User confirmed web search will use **Reduce keywords**, not Map keywords, because:
- Reduce keywords are theme-level (better search scope)
- Generated after clustering (more focused)
- Higher quality (as shown above)

## Recommendation

### Remove Map keywords field

**Reasons**:
1. **Minimal utility**: Only used as hint, Reduce LLM generates better keywords from title+summary alone
2. **Cost reduction**: Reduces Map LLM workload by ~10-15% (fewer fields to generate)
3. **Simplification**: One less field to validate and maintain
4. **Future-proof**: Phase 2 will use Reduce keywords anyway

**Impact**:
- ✅ No functionality loss (Reduce generates better keywords)
- ✅ Map stage faster and cheaper
- ⚠️ Reduce LLM loses minor hint (but title+summary contain same info)

### Alternative: Keep as optional hint

If concerned about removing hint entirely, could:
1. Mark as `Optional[list[str]]` (non-required)
2. Update Map prompt to make keywords optional
3. Let LLM decide when they're useful

But this adds complexity without clear benefit.

## Decision Criteria

**Keep Map keywords if**:
- Reduce keyword quality degrades significantly without hint (requires A/B test)
- Evaluation shows Map keywords improve Reduce recall/precision

**Remove Map keywords if**:
- A/B test shows no significant quality difference
- Cost/complexity reduction is prioritized

## Next Steps

### Option A: Remove immediately (recommended)
1. Remove `keywords` field from `MappedIssue` model
2. Remove keyword generation from Map prompt
3. Update reduce_stage.py to not show keywords hint
4. Run pipeline test to verify quality
5. Compare results with current baseline

### Option B: A/B test first (safer but slower)
1. Run pipeline with Map keywords (current)
2. Run pipeline without Map keywords (modified)
3. Compare Reduce keyword quality
4. Decide based on data

### Option C: Keep for now (status quo)
- No changes
- Revisit during Phase 2 implementation
