# Handoff — price-volume-entry-opportunity-review

- 갱신: 2026-10-13 09:59 KST · Branch: feature/scorecard-strategy-position-separation · Status: 새 에이전트 검토 시작 확인
- 체크아웃: `/Users/al03229901/Develop/My/invest-jarvis` · HEAD: `8c604029cae774f5bdd802a1cb98dc6aba0783f4`
- 인수 세션: `term_26ded214-0232-4fc8-b5e1-32e22c3109a7` · 발신 세션: `term_7aaff85b-fe77-43a9-8da5-6b392340ec3e`
- 인수 워크트리: `/Users/al03229901/orca/workspaces/invest-jarvis/price-volume-rule-review` · Branch: `feature/price-volume-rule-review`
- 인수 worktree ID: `728e7395-d9a4-43b8-8ce0-b2f6e72a93b8::/Users/al03229901/orca/workspaces/invest-jarvis/price-volume-rule-review`
- 새 워크트리는 기본 `origin/main`에서 만들었다. **검토 기준 코드는 위 원본 체크아웃의 미커밋 상태**다. 원본은 읽기 전용, 검토 문서는 인수 워크트리에만 작성한다.

## 목표
Tennis Ball 가점과 급락한 과거 breakout의 `EntryOpportunity=ALLOW` 문제에 대한 외부 연구를 현재 코드·사용자 합의에 대조한다. 채택할 원칙과 실험할 수치를 구분하고 설명 가능한 truth table(조건별 결과표)을 제안한다.

## 위임 범위
사용자 최신 요청은 “새 에이전트 열어서 핸드오프 시켜줘”다. **연구·설계 검토**를 이어받는다. 외부 보고서 수령은 모든 권고의 승인이나 구현 지시가 아니다. 코드·테스트와 필요한 원 출처를 읽고 사용자에게 한국어 존댓말로 권고를 설명한다. 코드 구현·실데이터 재실행·백테스트 실행·commit/push/merge는 시작하지 않는다.

## 지금까지
- Technical Score는 차트 측정, Observation은 관찰 과정, Signal은 특정 거래일 사건, EntryOpportunity는 그 사건을 오늘도 실행 가능한지 평가, PositionPlanner는 실제 수량 계산으로 분리했다.
- Strategy는 실제·가상 보유와 장부를 읽지 않는다. 가상 체결·stop·R·장부는 Backtest에만 있다. 동일 chart prefix·version·parameter면 같은 결과를 낸다.
- PostgreSQL Strategy 저장·cache는 제거한 미커밋 상태다. Stock Report DB는 별개다. 과거 history는 차트에서 재계산한다.
- 장중 `PROVISIONAL` Signal·EntryOpportunity·PositionPlan도 사용·표시한다. Backtest는 `FINAL`만 사용한다. immutable DB 저장을 다시 도입하지 않는다.
- 10/12 check·analyze·brief 공통 출력에 전체 Signal/Opportunity Evidence·원인·관측값·기준값과 최근 5일 점수 상세를 연결했다. 근거: worklog 22:01·22:14.
- 당시 pytest **1,864 passed / 15 deselected**, Ruff·변경 format·diff PASS, 실제 `jarvis check NVDA` 성공을 기록했다. 이번 인계에서는 재실행하지 않은 과거 검증 결과다.
- 현재 관련·무관 dirty/untracked 변경이 많다. 모두 보존한다. 오래된 `docs/handoff/swing-w150-engine.md`는 V1·PR #62 시점이므로 최신 기준이 아니다.

## 현재 코드에서 확인된 것
| 항목 | 실제 동작 | 근거 |
|---|---|---|
| Tennis Ball/Egg | 오늘 음봉 + 이전 5봉 음봉 최소 2개, 거래량 비율 <0.5이면 +15, >1.5이면 -15. 반등·finality 검사 없음 | `src/tools/technical/components/volume.py:235` |
| 거래량 분모 | 오늘을 제외한 이전 봉들로 이미 계산함. 보고서의 t-1 기준 제안은 이 부분에서 기존 구현과 같음 | 위 파일 264행 |
| EntryOpportunity V2 | 최신 entry → correction/exit → age 20 → 시장 → bull & extension <=+5%이면 ALLOW. 하한·adverse path 없음 | `src/strategies/entry_opportunity.py:170` |
| Watch 시작 | SMA50>150>200·각 21일 기울기 양수·Supertrend 상승 + SMA50/150/200 또는 Supertrend 근접·종가 방어 | `src/strategies/swing_w150/signals.py` |
| Watch 유지/반등 | 초기 상승 gate를 매일 모두 다시 검사하지 않음 | 위 파일 570~628행 |
| 눌림 entry | watch 이후 종가>유효 지지선 & 이전 N봉 최고가. 현재 N=1이며 이미 parameter | `signals.py:587`, `parameters.py:31` |
| PositionPlanner | current Signal만 사용. 선택 Signal ID와 오늘 ALLOW source ID 일치해야 신규 수량 계산 | 최신 spec §12 |

## 외부 보고서와 미결
사용자 제공 **「가격·거래량 기반 매매 규칙 독립 검토 보고서」, 기준일 2026-10-12**의 핵심·수치·출처는 [연구 메모](../references/2026-10-12-price-volume-independent-review.md)에 있다. 원문 전체 복사본이 아닌 인계용 요약이며 아직 승인되지 않았다.

보고서는 B(저거래량 눌림은 후보 0점, 반등 확인 후 bullish evidence), old breakout adverse failure 종료, 새 pullback reversal의 새 기회를 추천한다. bounded ATR+구조, reversal 2봉, age 5/3봉은 초기 가설이다.

검토할 핵심 쟁점:

- FINAL-only를 모든 실시간 Signal·PositionPlan에 강제하면 기존 장중 사용 합의와 충돌한다. PROVISIONAL 현재 평가와 FINAL 확정 history를 구분한다.
- 보고서의 immutable FINAL 사건·Signal 당시 ATR 고정은 결정적인 차트 재계산으로 구현 가능하다. 자체로 DB 저장을 요구하거나 기존 합의와 충돌하는 것은 아니다. DB 재도입으로 해석하지 않는다.
- Technical Score가 +15를 위해 Swing Signal을 역참조하면 Tools→Strategies 방향이 뒤집힌다. 공통 차트 feature와 각 계층의 해석을 구분한다.
- Egg의 단순 해석을 비판한 연구가 -15 제거의 성과 우위까지 입증한 것은 아니다. 명칭·Evidence 수정과 weight 실험을 구분한다.
- 현재 extension 하한만 검사하면 과거 breach 후 회복한 old signal이 부활한다. prefix 경로와 최초 terminal 원인을 재계산해야 한다. 종가/저가, 만료 후 실패, PROVISIONAL breach의 가역성은 미정이다.
- 보고서의 소폭 하락 ALLOW와 미확인 소폭 하락 WATCH를 나눌 명시적 조건·우선순위가 없다.
- Watch 활성·반등 때 상승 gate 재검사, Supertrend 하락 역할, 다중 지지선 선택·갱신을 결정해야 한다.
- 반등 Signal만으로 volume +15를 붙일지 실제 후보·거래량 확인을 요구할지 미정이다. 점수 중복 보상도 검토한다.
- Opportunity invalidation은 실제 보유의 손절/매도 지시가 아니다. Backtest stop·실제 수량 정책으로 자동 전파하지 않는다.
- 과거 ALLOW의 화면 안내와 PositionPlanner current-only 수량 정책은 현재 별도다. 늦은 진입 수량 정책 변경을 추정 승인하지 않는다.

## 다음 행동

연구 메모와 최신 spec §4·7·8·12를 읽고 실제 코드에 대조한 **채택 권고 / 기존 합의와 충돌 / 백테스트 가설** 표 및 FINAL·PROVISIONAL이 구분된 EntryOpportunity truth table 초안을 사용자에게 제시한다. 숫자를 확정 정책처럼 쓰지 않는다.

## 참조 (읽기 순서)

1. `AGENTS.md`, `CLAUDE.md` — 한글 존댓말·설명 수준·uv·dirty 보존
2. `docs/references/2026-10-12-price-volume-independent-review.md` — 외부 연구
3. `docs/superpowers/specs/2026-10-06-strategy-signal-outcome-backtest-boundary-design.md` — 현재 책임·장중·기회·수량 계약
4. `src/tools/technical/components/volume.py`, `src/strategies/entry_opportunity.py`, `src/strategies/swing_w150/{signals,parameters}.py` — 실제 동작
5. `tests/strategies/test_entry_opportunity.py`, `tests/strategies/swing_w150/test_signals.py`, `src/backtest/swing_w150.py` — 현재 계약·체결 경계
6. `docs/worklog/swing-w150-engine.md` — 10/08 결정·10/12 검증

## 함정 · 하지 말 것

- 코드 수정·새 상태/DB/장부·commit/push/PR/merge 권한을 추정하지 않는다.
- 10/12 장중 ALAB·COHR·INTC 가격을 현재 가격으로 표시하지 않는다.
- 원문의 검색 citation marker는 이 세션에서 해석할 수 없다. URL 존재·원문 주장·실증 범위는 별도 확인 대상이다.
- Pro 모델·추가 에이전트 생성은 별도 요청 없이 하지 않는다. 이번 인수 에이전트가 작업 소유권을 이어받고 발신 에이전트는 멈춘다.
