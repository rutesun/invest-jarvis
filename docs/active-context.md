# Active Context

- **갱신**: 2026-10-01 16:03 (PR #62 생성 — 검토대기)
- **Branch**: feature/swing-w150-engine (워크트리: swing-w150-engine)
- **진행 단계**: 구현·검증·문서·commit·push 완료 → PR #62 검토대기

## 지금까지
- 위임 작업: 백테스트로 확정한 v3(S 50일 신고가 + D 바닥 경로 + 30주선 2일/−1R 청산 + 과열 20일선 규칙)를 엔진화(2단계)하고 check/brief에 참고 표시(3단계). 기존 action은 덮어쓰지 않음.
- 계획서: `docs/superpowers/plans/2026-09-30-swing-w150-engine.md` (strategies 레이어 구조 반영 완료).
- 확인: jarvis 지표와 백테스트 지표 식 차이(ATR·슈퍼트렌드). 제품 데이터는 3년(워밍업 250봉 뒤 약 2년 replay).

## 핵심 결정
- 재료는 `src/tools/technical` 한 곳에 두고 재사용, 해석(레시피·상태)은 pipelines 쪽.
- 지표는 jarvis `IndicatorCalculator`로 통일하고 v3 성과를 재검증(옵션 A).

## 추가 결정
- 전략은 별도 레이어 `src/strategies/swing_w150/` (tools만 import). CLAUDE.md·AGENTS.md 표 갱신 완료.
- 한국·미국 모두 표시, 미검증 표기 없음.
- 정답지: tests/fixtures/swing_w150/{COIN,AMAT,PYPL,UPST} (jarvis 지표판 기준).

## 완료
- 코드: src/tools/technical/{indicators.py(7컬럼),pivots.py}, src/strategies/swing_w150/{rules,engine,models}.py, quick_check·brief 표시.
- 테스트: 골든 4종목, 상태·규칙·요약·pivots, check/brief 표시·판정 불변. 전체 1430 passed, ruff clean.
- 실데이터: NVDA 보유(S), 005930 대기(S) 288,000, HOOD 대기(S).
- 문서: change record `docs/changes/swing-w150-strategy-engine.md` + INDEX, FEATURES.md §13, CLAUDE.md·AGENTS.md 레이어 표, worklog.
- 재검증: `uv run pytest -q` 1430 passed, `ruff check` 통과, `ruff format --check` 375 files formatted.
- 기능 commit: `4f20f57` (`feat(strategy): add SWING_W150 engine`).
- PR: https://github.com/rutesun/invest-jarvis/pull/62

## 다음 행동
- 인계 문서: `docs/handoff/swing-w150-engine.md`.
- PR #62 review·CI 확인 후 피드백 반영 또는 merge.
- 후속 후보: 한국 종목 백테스트, tools/brief → pipelines/brief 이동, tools/technical/strategies 이름 정리, screener 신호 종목 발굴.
