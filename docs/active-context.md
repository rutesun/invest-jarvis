# Active Context

- **갱신**: 2026-09-11 (바닥 그라데이션 구현·튜닝·문서 완료)
- **Branch**: feature/bottoming-gradient (워크트리: bottoming-gradient)
- **진행 단계**: 구현·테스트·튜닝·change record 완료 → 커밋 후 PR 승인 대기

## 지금까지
- 문제: adjusted score가 SMA50 위/아래에 연동돼, 저점을 계단식으로 높여도 avoid(-90) 고정 →
  SMA50 재탈환 순간 hold(+105)로 급점프(BE 2026 7/28~9/8 실증).
- 구현: 바닥 구조를 as-of 안전하게 계량해 avoid를 accumulate 밴드까지만 상한 있게 완만화.
  - `src/tools/technical/bottoming.py`(신규): higher_low(10/30)·bullish_divergence·volume_dry·
    momentum_improving 4신호, MIN_SIGNALS=3, 상한 있는 bonus. `BottomingThresholds` 상수.
  - `aggregator.py`: `bottoming` 인자 + `bottoming_gradient_bonus` 규칙 + `accumulate` 액션.
    CEILING=-15, ACCUMULATE_FLOOR=-40. SMA50 아래 + forced_action 없을 때만 적용.
  - downstream: analyzer tri-state accumulate→중립, analyze_decision factor→5(neutral).
- 튜닝: 평가세트(BE/NVDA/LULU) 스윕 → (MIN3, 10/30) 채택. LULU 가짜 accumulate 8→0.
- 검증: 신규 테스트(bottoming 15 + regression 4 + aggregator 6 + 매핑 2), 전체 1348 passed, ruff clean.

## 핵심 결정
- accumulate를 1급 VerdictAction으로 추가(라벨 노출), 단 new_entry_allowed=False·상한 -15로 규율 유지.
- 상한 가점은 이평 아래에서만 → 강세주(NVDA) 불변, 하락주(LULU) 가짜 바닥 배제.
- worklog `bottoming-gradient.md`에 설계·튜닝 근거 기록.

## 완료 (박제)
- 코드: bottoming.py, aggregator/scorer/models, analyzer/analyze_decision.
- fixtures: be_bottoming / nvda / lulu (2025-01-01~2026-09-09).
- 문서: change record `bottoming-gradient.md` + INDEX, FEATURES.md 갱신, worklog.

## 다음 행동
- 격리 워크트리 커밋(승인 불필요).
- push/PR/merge는 사용자 승인 후(gec-create-pr).
- (선택) 가중치(W_HL/DIV/VD/MO) 추가 튜닝은 밴드 내 lift만 좌우 — 현재 초기값 유지.
