# Change Record: NH 국내·미국 계좌와 매매일지

**Status**: In Progress
**Date**: 2026-11-06
**PRs**: -
**Type**: feat

## Why

주 사용 증권사의 실제 보유와 Jarvis가 사용하는 수동 보유 설정 사이의 차이를 줄이고, 앱에서 거래한 사실을 투자 이유·계획·복기와 함께 관리한다.

## Changes

### Added

- 국내·미국 NH 잔고 조회와 실제 보유 기준 브리핑을 추가한다.
- 국내 누적 체결과 미국 일별 매매내역을 중복 없이 수집하는 로컬 거래 장부를 추가한다.
- 투자 건별 거래 흐름과 이유·무효화 조건·추가매수 조건·복기를 연결한다.
- 종목·기간·시장·복기 여부·태그 필터와 수동 전략 분리, 로컬 Markdown 내보내기를 제공한다.

## Impact

기존 YAML 기반 brief는 기본 동작을 유지한다. NH 연결은 별도 명령·옵션으로 사용하며 키 이름은 NS_APP_KEY와 NS_APP_SECRET이다. 개인 거래 장부는 git에서 제외된 data/broker에 저장한다.

## Constraints

주문 전송·주문 가능 금액 기반 매수 수량 제한·Notion 자동 전송은 포함하지 않는다. 공식 예제 fixture 검증과 실제 계좌 연결 검증을 구분한다. 미국 거래 반영 지연과 날짜 단위 기록의 묶음 한계를 표시한다.

## Validation

- 최종 관련 테스트 329개, 변경 Python 파일 Ruff, CLI help 및 독립 재리뷰를 통과했다. 재리뷰의 잔존 Critical/Important/Minor는 0건이다.
- 기본 전체 회귀는 3,623 passed, 1 skipped, 15 deselected였다. 전체 실행 중 추가한 잔고·수동 경계 보강은 최종 관련 329개로 별도 재검증했다. 기존 Pydantic/pandas 경고 2개가 있다.
- 공개 NH 예제와 합성 paging/장애 응답을 사용해 provider→SQLite→CLI 경로, 소수점·메모·수동 경계 보존을 검증한다. 개인 raw 응답은 fixture에 포함하지 않는다.
- 실계좌 인증·계좌·국내/미국 잔고와 최근 7일 거래 조회를 별도로 확인했다. 전체 시세·LLM을 포함하는 실계좌 brief 실행은 검증 범위에 포함하지 않는다.
- 실제 미국 거래의 모든 표기 변형이나 같은 날 정확한 체결 순서를 검증한 것으로 해석하지 않는다. 제공된 거래 전후잔고와 장부가 맞지 않으면 불완전 이력을 표시한다.

## Related

- [설계](../superpowers/specs/2026-11-06-nh-account-journal-design.md)
- [구현 계획](../superpowers/plans/2026-11-06-nh-account-journal.md)
- [작업 일지](../worklog/nh-account-journal.md)
