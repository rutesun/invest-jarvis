# NH 계좌 연동과 매매일지 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 국내·미국 NH 잔고 기반 브리핑 및 거래 자동 수집·투자 건별 메모/복기를 제공한다.
**Architecture:** NH provider가 응답을 검증하고 Decimal 기반 계좌 모델을 반환한다. pipeline이 로컬 설정과 실제 잔고를 결합하고, SQLite 장부는 거래 사실과 사용자 기록을 분리한다. 기존 Strategy/시세 provider는 유지한다.
**Tech Stack:** Python 3.12+, 기존 httpx/Typer, stdlib SQLite/Decimal, uv/pytest.
**Spec:** docs/superpowers/specs/2026-11-06-nh-account-journal-design.md

## Global Constraints

- 주문 전송·주문 가능 금액 기반 수량 제한·Notion 자동 전송은 제외한다.
- 원본 디렉터리의 branch·파일·.env를 변경하지 않는다. a7b0 격리 worktree의 feat/nh-account-journal 브랜치에서만 구현·커밋한다. 사용자가 별도 worktree 커밋을 명시 승인했다. push/merge는 하지 않는다. 초기 dirty 복사 baseline은 별도 보관 후 제거했고 이 브랜치만 main@abd0715로 fast-forward했다.
- 비밀·계좌 원문은 출력/fixture/문서/장부 ID에 노출하지 않는다. 보유·금액은 Decimal이며 소수점 절삭을 금지한다.
- 최종 테스트는 이 worktree 전용 `.venv`에서 `uv run --no-sync ...`로 실행한다. 초기 공유 환경 결과와 구분하며 원본 환경은 변경하지 않는다.
- source doc 캡처: /tmp/jarvis-nh-contracts/*.json. 공개 예제이며 실계좌 증거가 아니다.

## Review Focus

- 날짜가 없는 누적 체결의 같은 날 매도/재진입 순서를 임의로 단정하지 않는다.
- 계좌/통화/시장/신용 구분이 다른 기록을 합치지 않는다.
- 페이지 중간 실패·반복 cts·업무 실패를 빈 잔고/동기화 완료로 표시하지 않는다.
- 부분 체결이 늘어도 메모와 수동 분리를 유지한다.
- 해외 `총자산`과 국내 `총자산` 중복, 정규장/시간외 가격, 조회/실거래 날짜의 의미를 구분한다.

### Task 1: NH provider와 계약

**Files:** Create src/providers/nhplug/{__init__,models,client}.py, tests/providers/test_nhplug.py, tests/harness/nhplug_contract.py, tests/fixtures/nhplug/*, .env.example 추가.
**Interfaces:** NHClient는 env 기반 생성 및 accounts(), balances(account), trades(account,start,end)를 제공한다. 외부에서 주입 가능한 httpx transport로 네트워크 경계만 대체한다. 모델의 세부 명칭은 한 모듈에 명시해 후속 작업이 import한다.

- [x] 공식 예제를 fixture로 보존하고 source README를 작성한다. fixture 계약은 공통 conftest를 오염시키지 않도록 fixture loader에서 호출한다.
- [x] 인증 재사용, paging, 오류, 국내 현금/신용, 미국 통화/소수점, 체결수량 0 제외를 검증하는 실패 테스트를 작성·실행한다.
- [x] 고정 NH endpoint, private token cache+발급 잠금, 응답 검증과 시장별 정규화를 구현한다. 계좌 식별자는 hash/마스킹이고 raw account repr는 숨긴다.
- [x] `uv run --no-sync pytest tests/providers/test_nhplug.py -q`를 실행해 통과를 확인한다.

### Task 2: 거래 장부와 투자 건

**Files:** Create src/tools/trades/{__init__,journal,render}.py, tests/tools/trades/test_journal.py.
**Interfaces:** provider가 반환한 거래 모델을 sync하여 stable trade ID와 case ID를 생성한다. list/show/note/split/export에서 같은 SQLite 경로를 사용한다. SQLite 파일은 data/broker 아래이고 메모는 거래 fact와 별도 table이다.

- [x] 동일 거래 재수집·누적 부분 체결 증가·메모 보존·동기화 원자성·미국 소수점·매도 시작 이력·재진입·수동 분리를 실패 테스트로 고정한다.
- [x] 장부 및 투자 건 grouping을 구현한다. 날짜만 있으면 묶음의 정밀도 한계를 노출하며 진입/청산을 확정하지 않는다. 기존 과거 이력이 새로 들어와도 메모 identity가 변하거나 사라지지 않게 한다.
- [x] 이유·무효화 조건·추가매수 조건·태그·복기·source link 및 analysis provenance를 저장하고 Markdown으로 조회/내보낸다.
- [x] `uv run --no-sync pytest tests/tools/trades -q`를 실행해 통과를 확인한다.

### Task 3: 실제 보유 기준 브리핑

**Files:** Create src/pipelines/broker_account.py; modify src/tools/playbook/holdings.py, src/pipelines/brief.py, src/tools/brief/{models,render}.py; tests/pipelines/test_broker_account.py, 관련 기존 brief 테스트.
**Interfaces:** merge NH balances with HoldingsConfig in memory. Broker summary is explicit optional metadata so old YAML brief behavior stays intact. 원본 YAML·Strategy에 NH 의존성을 추가하지 않는다.

- [x] NH에 없는 YAML 보유 제거·stop/watch 보존·동일 ticker 현금/신용·시장 실패·소수점 수량 미지원 경고를 테스트한다.
- [x] 정수 보유만 기존 planner에 전달한다. 소수점은 분석/실제 수량을 표시하되 planner 수량은 계산하지 않고 경고한다.
- [x] 보유별 NH 수량·매입단가·평가액·손익과 조회시각을 출력한다. source별 합계를 별도 표시하고 원화/외화를 더하지 않는다.
- [x] `uv run --no-sync pytest tests/pipelines/test_broker_account.py tests/pipelines/test_brief.py tests/tools/brief tests/tools/playbook/test_holdings.py tests/position -q` 통과를 확인한다.

### Task 4: CLI와 사용 문서

**Files:** Create src/cli/broker.py, src/cli/trades.py; modify src/cli/main.py의 Typer 등록 및 brief 연결; create tests/cli/test_broker_cli.py, tests/cli/test_trades_cli.py; update docs/{CLI_USAGE,FEATURES}.md, docs/changes/{nh-account-journal,INDEX}.md.
**Interfaces:** spec의 CLI 사용법을 제공하고 --db로 장부 경로를 격리할 수 있다. --account는 표시용 stable identifier로 선택하며 계좌 원문을 argument로 요구하지 않는다.

- [x] help뿐 아니라 MockTransport→provider→장부→CLI 출력의 end-to-end와 note/split/export, 조회 실패 exit code, 예전 brief default를 테스트한다.
- [x] `broker accounts/holdings`, `brief --broker nh --account`, `trades sync/list/show/note/split/export`를 연결한다. --broker 미지정 시 기존 YAML 동작 유지. sync 기간은 명시적으로 받고 전체 페이지 조회 후 한 번에 저장한다.
- [x] CLI 사용법·검증 범위·미국 결제 반영 지연·불완전 이력·소수점 대응 한계·private 저장 위치를 문서화한다.
- [x] 관련 전체 테스트와 CLI --help, pytest 기본 suite를 실행한다. 기존 실패는 이름과 원인을 구분해 보고한다.

### Task 5: 통합 검토와 실계좌 검증 상태

- [x] 다른 reviewer가 NH 추가분만 독립 검토한다. 복사한 baseline 변경을 이번 구현으로 오인하지 않는다.
- [x] 발견된 중요 결함은 재현 테스트 후 수정한다. 원래 디렉터리 dirty hash를 다시 확인한다.
- [x] 실제 인증/조회는 로컬 .env의 NS_ 키를 출력 없이 읽는 별도 검증이다. 개인 raw 응답은 저장하지 않고 계좌/시장별 성공 여부만 기록한다. 실패하면 fixture 검증과 실제 연동 검증을 구분해 보고한다.
- [x] 완료 상태·실행 위치·사용 명령·남은 한계를 사용자에게 보고한다. 사용자가 승인한 별도 worktree 브랜치에서만 commit하며 push/merge는 실행하지 않는다.

## 최종 검증

- 기본 전체 회귀: 3,623 passed, 1 skipped, 15 deselected.
- 잔고·수동 경계·실계좌 RP 후속 보강을 포함한 최종 관련 테스트: 331 passed.
- Ruff, CLI help, 독립 최종 리뷰(C0/I0/M0), 원본 clean main@abd0715와 비밀값 유출 검사를 확인했다.
- 실계좌 최근 7일 국내·미국 거래 조회·동기화·재수집 중복 방지·Markdown 내보내기와 실제 시세 기반 brief --no-llm 실행 성공. 최종 브리핑은 종료코드 0, 종목 조회 실패 0이며 RP는 주식 분석 대상에서 제외해 별도 표시했다. 개인 raw 응답은 보관하지 않았으며 LLM 문장 생성은 실행하지 않았다.
- 커밋은 이 worktree 브랜치에 한정한다. push/merge는 하지 않는다.
