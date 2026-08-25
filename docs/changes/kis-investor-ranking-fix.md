# Change Record: 외국인·기관 순매수 순위 복구 (get_investor_ranking)

**Status**: Draft
**Date**: 2026-08-25
**PRs**: #{PR 번호}
**Type**: fix

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

스크리너 유니버스의 외국인·기관 순매수 소스(`KISProvider.get_investor_ranking`)가 **항상 빈 리스트를 반환**하고 있었다. KIS `foreign-institution-total`(FHPTJ04400000) 호출이 화면분류코드 `16174`(잘못) + 필수 파라미터 `FID_RANK_SORT_CLS_CODE` 누락으로 `rt_cd=2`(ERROR INPUT FIELD NOT FOUND) 에러를 냈는데, HTTP 200이라 예외도 안 나고 조용히 0건을 내려보냈다. 결과적으로 이 소스는 유니버스에 한 종목도 기여하지 못했다.

## What

1. **파라미터 계약 수정**: `FID_COND_SCR_DIV_CODE` `16174` → `16449`, `FID_RANK_SORT_CLS_CODE="0"`(금액순) 추가. 라이브로 rt_cd=0 · 30종목 반환 확인.
2. **투자자별 클라이언트 정렬**: 이 엔드포인트는 한 응답에 종목별 외국인(`frgn_ntby_*`)·기관(`orgn_ntby_*`) 순매수를 모두 담아 준다. 서버 정렬 의미가 불투명해, `investor_type`에 맞는 순매수 금액으로 클라이언트에서 내림차순 정렬하고 순매수(>0)만 top_n 반환 — 외국인/기관 두 순위가 항상 정확하도록.
3. **조용한 실패 제거**: `rt_cd != "0"`이면 빈 리스트를 조용히 내리지 않고 `logger.warning`으로 표면화(CLAUDE.md 경계 계약 원칙).

## Before / After

```
Before: FID_COND_SCR_DIV_CODE=16174, FID_RANK_SORT_CLS_CODE 없음
        → rt_cd=2, output=[] → get_investor_ranking() == []  (항상)
After:  FID_COND_SCR_DIV_CODE=16449, FID_RANK_SORT_CLS_CODE=0
        → rt_cd=0, foreign 30 / institution 30 (금액순, 순매수만)
```

## Impact

- 스크리너 유니버스에 외국인·기관 순매수 상위 종목이 실제로 포함된다(KIS 키 있을 때). CLI 인터페이스·환경변수 변화 없음.

## Constraints

- 이 엔드포인트의 일별 스냅샷 특성은 그대로(당일 순매수 집계). 순매수 리더가 "이미 상승한 종목"에 치우치는 구조적 한계는 코드 문제가 아니므로 다루지 않는다(→ 광역 바닥 발굴은 ROADMAP 후속).

## Related

- 설계/검증: `docs/worklog/bottom-watch-signal.md` (2026-08-25 Decision)
- ADR: 없음
- FEATURES.md: 해당 없음(내부 provider 버그 수정)
- 후속: 광역 저점 근접 유니버스 + 매집 시작 탐지(ROADMAP Task 15 후속)
