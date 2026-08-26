# Change Record: brief 종목명 리졸버 (TickerNameResolver)

**Status**: Draft
**Date**: 2026-08-26
**PRs**: #{PR 번호}
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

`jarvis brief` 출력이 종목을 **티커/코드**로만 표기해(예: `257720.KS`) 한눈에 어느 종목인지 알기 어려웠다. 종목명을 붙이려면 yfinance `get_quote`(종목당 1~2초)를 매 실행 반복해야 해 느리다. 종목명은 거의 바뀌지 않으므로 캐시로 해결한다.

## What

1. **`TickerNameResolver`** (`src/tools/brief/name_resolver.py`): ticker→종목명 조회를 180일 영속 캐시(`UserMappingCache` 재사용, 전용 캐시 파일)로 감싼다. 캐시 우선, 없으면 yfinance 조회 후 저장. 실패 시 None → 렌더러가 코드로 graceful fallback.
2. **KR 시장 접미사 처리**: 사전 시장 정보가 없어 `.KS`(KOSPI) → `.KQ`(KOSDAQ) 순 시도, 이름이 잡히는 첫 심볼 사용. KIS 시세는 종목명 필드가 비고 한글명 tr_id는 앱키 미승인이라 US·KR 모두 yfinance로 통일.
3. **오염된 이름 필터**: yfinance는 잘못된 접미사에 예외 대신 `quoteType='MUTUALFUND'`인 fuzzy 결과(쓰레기 shortName)를 준다. `YFinanceProvider.get_quote`에 `quote_type`를 노출하고, resolver가 `EQUITY`/`ETF`만 통과시켜 오염을 거른다.
4. **배선**: `BriefItem.name` 추가, `BriefPipeline`이 resolver로 이름을 채우고, `render`가 `"종목명 (코드)"`로 표기(이름 없으면 코드만).

## Before / After

```
Before (brief 종목 헤더):  257720.KS — 거부
After  (brief 종목 헤더):  실리콘투 (257720.KS) — 거부
```

## Impact

- `jarvis brief` 종목 표기에 종목명 병기. 최초 1회 yfinance 조회 후 `~/.cache/invest-jarvis/ticker_names.yaml`에 캐싱(180일). 환경변수·마이그레이션 없음.

## Constraints

- 종목명 소스는 yfinance로 통일(KIS 한글명 tr_id 미승인). 조회/캐시 실패는 예외 아니라 코드 fallback으로 degrade.

## Related

- ADR: 없음
- FEATURES.md: {확인 필요 — brief 섹션에 종목명 표기 반영 여부}
- 후속: 없음
