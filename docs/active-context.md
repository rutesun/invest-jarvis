# Active Context

- **갱신**: 2026-08-25 (턴어라운드 구현 완료)
- **Branch**: feature/bottom-watch-signal (워크트리: .worktrees/bottom-watch-signal)
- **진행 단계**: 턴어라운드 신호 3표면 배선 완료 → change-record/PR 대기

## 지금까지
- bottom_watch(역추세 바닥 예측 신호) → 편향 없는 표본 검증 실패(과적합). 보류.
- 재검토(Ouroboros 인터뷰) + 검증 관문 실행 → 턴어라운드 스코어도 나이브 기준선 미통과(예측 알파 없음). 단, check 확인 분리는 대부분 기계적 상관.
- 사용자 결정: "판단(기사·시장)은 내가, 신호만 줘" → 턴어라운드를 **발굴·해석 보조 도구**로 구현(예측 아님).
- 구현 완료:
  - 코어 `src/tools/technical/turnaround.py` — 4마커 as-of 안전 점수화, TurnaroundSignal.
  - check(quick_check 한 줄), screen(--turnaround 발굴 모드), brief(BriefItem.turnaround) 배선.
  - 테스트 14개, 전체 1305 passed. ruff 통과. 커밋 02debca.

## 핵심 결정
- 예측 알파 아님을 docstring·CLI 문구에 명시. 마커 내역+check확인+손절선 제공, 최종 판단은 사용자.
- 4마커는 AND 아니라 점수화(recall 중심), threshold 2.

## 다음 행동
- change-record 작성(docs/changes/) + INDEX 갱신 → pre-push 통과.
- PR 생성(gec-create-pr) — main 병합.
- (선택) 마커 가중치/임계값 실사용 튜닝.
- 참고: `docs/superpowers/specs/2026-08-24-bottom-watch-design.md`, `docs/worklog/bottom-watch-signal.md`, ROADMAP Task 15.
