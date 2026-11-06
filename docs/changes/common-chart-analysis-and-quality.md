# Change Record: 공통 차트 분석과 실험적 Quality

**Status**: In Progress
**Date**: 2026-11-06
**PRs**: 미생성
**Type**: feat

## Why

전략마다 중복 계산하던 차트 사실을 공유하면서 각 전략의 판단·점수·수량 정책을 보존합니다. 차트 상태를 설명하는 별도 Quality와 전략별 독립 수량을 기존 분석 명령에서 함께 확인할 수 있도록 연결합니다.

## What

- 공통 Event(조건 발생)·Observation(상태 관측)·Risk(위험 조건)와 FactRef(계산 근거 참조)를 도입하고 기존 전략의 정책·날짜·ID·근거를 유지합니다.
- 추세·구조·모멘텀·거래량 참여의 4축 Quality, 현재 실측과 전일차, 날짜별 원점에서 다시 계산한 5일 이력을 제공합니다. Technical Score와 구별하며 매매 등급으로 사용하지 않습니다.
- `check`·`analyze`·`brief`에서 공통 사실·Quality를 한 번 표시하고 전략별 판단과 독립 수량을 연결합니다. 기본 화면은 현재 유효 상태 중심이며 과거·해소 이력과 상세 근거는 상세 옵션에서 제공합니다.
- API가 반환한 일봉의 날짜·값으로 공통 입력을 검사합니다. 외부 거래일 달력으로 없는 날짜를 생성하거나 결측으로 추정하지 않으며, 반환값 오류·중복·미확정과 최소 봉 수는 검사합니다.
- Quality 입력이 부족하면 기존 공급자의 3y 입력을 최대 한 번 보충합니다. 원래 전략 raw는 보존하며 겹치는 유효 OHLCV가 다르면 Quality를 unavailable로 표시합니다.
- 진입 구조 위험의 발생일·첫 확정일을 현재 평가일·가격과 구분합니다. 표시 metadata는 기존 저장 payload에서 제외합니다.

## Before / After

```text
Before: 전략별 차트 계산·Technical Score 중심 출력
After:  공통 차트 사실 → 현재 상태·Quality 4축·주요 가격대·5일 변화
        → 전략별 기존 판단과 독립 수량
```

## Impact

각 전략은 같은 보유·계좌 입력에서 별도 수량을 계산합니다. 전략 간 수량을 합산하거나 대표 전략을 선택하지 않습니다. Quality가 null이어도 기존 전략 평가를 계속 표시합니다. LLM에는 계산된 설명 자료를 전달하고 규칙이 정한 행동은 유지합니다.

## Constraints

- Quality 가중치·정규화는 실험적 수치입니다. 점수 분포·민감도·예측력 연구를 완료하지 않았고 매매 채택 근거로 사용하지 않습니다.
- API의 행 전체 누락은 휴장과 구분하지 않습니다. 2년 입력 구간, 계산 220봉·공개 FINAL 252봉, 보충 overlap 검사는 유지합니다. 연구 Backtest의 독립 입력 계약은 유지합니다.
- 독립 날짜·범위 서비스의 live raw 계약은 `STUB_ONLY`입니다. 기존 분석의 normalized 입력 검증은 fresh raw transport 검증과 구별합니다.
- 재계산 결과 DB·영속 cache·backfill을 추가하지 않습니다. 기존 진단 기록 계약과 전략별 수량 정책을 보존합니다.

## Related

- [현재 기능](../FEATURES.md#공통-차트-분석과-실험적-quality)
- [아키텍처와 책임](../ARCHITECTURE.md#공통-차트-사실과-quality의-책임)
- [check HTML 출력](check-text-html-output.md)
