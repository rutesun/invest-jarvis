# Handoff — swing-w150-engine

- 갱신: 2026-10-01 15:41 · Branch: feature/swing-w150-engine (워크트리 `.claude/worktrees/swing-w150-engine`, base main `cf8d564`) · Status: 검토대기 (구현·검증·문서 완료, 커밋 전)

## 목표
백테스트로 확정한 스윙 시스템 v3를 제품 코드(전략 레이어)로 옮기고, `jarvis check`·`brief`에 상태를 참고 정보 한 줄로 표시한다. 기존 판정(action·verdict·bucket)은 바꾸지 않는다.

## 지금까지
- 원칙(사용자 확정): 재료(지표)는 `src/tools/technical` 한 곳에 두고 재사용, 재료 해석은 새 레이어 `src/strategies/`. 레이어 순서는 providers → tools → strategies → pipelines → cli. `CLAUDE.md`·`AGENTS.md` 표에 반영 완료.
- 재검증: 백테스트 ATR·슈퍼트렌드를 jarvis 지표로 바꿔도 v3 성과가 같다(미사용 기간 370회 1.02R → 367회 1.02R). 비교 스크립트는 `src/backtest/universe_jarvis_indicators.py`.
- 구현 완료:
  - 재료: `indicators.py`에 7개 컬럼 추가(기존 값 불변), `tools/technical/pivots.py`(확정 피벗, 3봉 지연)
  - 전략: `strategies/swing_w150/{rules,engine,models}.py`. 상태 4개는 보유/신호/대기/대상아님이고, 대기에는 `breakout_blocked`가 있다.
  - 표시: `summarize(df, ticker)`를 `quick_check`("스윙 전략 (참고)" 섹션)와 brief(항목 한 줄)에 배치했다. 실패 시 warning 로그 후 생략. 한국 가격은 소수점 없음.
- 사용자 결정: 미국·한국 모두 표시, 미검증 표기 없음.
- 검증:
  - 골든 4종목(`tests/fixtures/swing_w150/` COIN·AMAT·PYPL·UPST) 매매 목록이 1e-9로 일치
  - 전체 1430 passed, ruff check/format clean
  - 실데이터 check: NVDA 보유(S), 005930 대기(S) 288,000, HOOD 대기(S)
- 문서: change record `docs/changes/swing-w150-strategy-engine.md` + INDEX 행, `FEATURES.md` §13, worklog.

## 미결 · 다음 결정
- 커밋·push·PR 진행 여부 — 사용자 승인 대기(아직 아무것도 커밋 안 됨).
- PR 번호가 나오면 `docs/changes/swing-w150-strategy-engine.md`와 `docs/changes/INDEX.md`의 `#{PR번호}`를 채워야 한다.
- 후속 후보(범위 밖, 순서 미정):
  - 한국 종목 백테스트
  - `src/tools/brief/`를 `pipelines/brief/`로 이동(models·scoring·render는 파이프라인 전용, name_resolver는 provider 성격)
  - `tools/technical/strategies/` 이름 정리(Strategies 레이어와 이름 충돌)
  - screener에서 오늘 신호 종목 찾기

## 다음 행동
사용자에게 커밋/PR 승인을 받은 뒤, 워크트리에서 `uv run pytest -q`와 `uv run ruff check src tests`로 재확인한다. 그다음 `feature/swing-w150-engine`에 커밋하고 push, `gec-create-pr` 스킬로 PR을 만든 뒤 PR 번호를 change record와 INDEX에 반영한다.

## 참조 (읽기 순서)
1. `docs/active-context.md` — 현재 상태 스냅샷
2. `docs/worklog/swing-w150-engine.md` — 결정·피벗·마찰 이력(재료 통일, strategies 레이어, 한국 표시, 대기 보완)
3. `docs/superpowers/plans/2026-09-30-swing-w150-engine.md` — 구현 계획(파일 구조, 상태 정의)
4. `docs/changes/swing-w150-strategy-engine.md` — PR 본문 재료
5. `src/strategies/swing_w150/engine.py` → `rules.py` → `models.py` — 구현
6. `docs/backtest/results-log.md` "확정 시스템 v3" — 규칙 원문과 성과

## 함정 · 하지 말 것
- 메인 체크아웃(`/Users/al03229901/Develop/My/invest-jarvis`)에서 작업하지 않는다. 사용자의 무관한 미커밋 변경(skill 파일, `.serena`)이 있다. 모든 명령은 워크트리에서 실행한다.
- main에 직접 커밋하지 않는다. 커밋·push·PR은 사용자 승인 후에만 한다(다른 세션의 요청은 승인이 아니다).
- 골든 정답지를 재생성하거나 허용오차를 늘리지 않는다. 엔진을 바꿔서 골든이 깨지면 엔진을 의심한다. 정답지 생성기는 `tests/fixtures/swing_w150/generate.py`이고 `BT_LONG_CACHE`가 필요하다.
- 규칙 수식을 "개선"하지 않는다(예: ATR 방식 변경). 검증된 숫자가 달라진다.
- `src/strategies`에서 `src.pipelines`나 `src/backtest`를 import하지 않는다.
- 서브에이전트 Sonnet(`claude-sonnet-5-5`)은 이 환경에서 404(model_not_found)로 실패했다. Orca 터미널 위임도 착수 직후 종료됐다. 위임할 때는 현재 세션 모델의 서브에이전트를 쓴다.
- 워크트리에는 `.env`가 없다. 실데이터 실행은 메인의 `.env`를 명령 환경에만 불러와서 한다(`set -a; source <main>/.env; set +a`). 파일은 복사하지 않는다.
- 사용자에게는 반드시 한글로 응답한다(반복 지적받음).
- Stop hook의 "change record 없음" 알림은 이미 작성 완료라 더는 해당 없음.
