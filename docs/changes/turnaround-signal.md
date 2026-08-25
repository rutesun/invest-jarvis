# Change Record: 턴어라운드 신호 (발굴·해석 보조)

**Status**: Draft
**Date**: 2026-08-25
**PRs**: #{PR 번호}
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

기존 `check`(추세 확인형 스코어링)는 정확·안전하지만 하락에서 반등하는 바닥을 늦게 잡는다. "역추세 바닥을 예측하는 신호"(bottom_watch)를 시도했으나 편향 없는 표본 검증에서 시드 2종목 외 거의 발화하지 않아(대형주 30종목×3년 1건, 변동성주 6종목×1년 0건) 과적합으로 폐기했다. 이후 턴어라운드 스코어 자체도 나이브 기준선("3개월 저점 대비 +10% 반등")을 이기지 못함을 확인했다. 결론적으로 **지표 기반 예측 알파는 없다.** 사용자 요구는 "기사·시장 판단은 내가 할 테니 턴어라운드 후보만 표면화해 달라"였고, 그에 맞춰 **예측이 아닌 발굴·해석 보조 도구**로 구현한다.

## What

1. **턴어라운드 스코어러 코어** (`src/tools/technical/turnaround.py`): 4마커(급락 후 과매도 반등, 20/50일선 재탈환, 거래량 수반 양봉, 저점 높이기)를 **AND가 아니라 점수화**한 순수함수 `score_turnaround(df) → TurnaroundSignal`. AND로 묶으면 bottom_watch처럼 거의 발화하지 않으므로, "소량 테스트" 전제(정밀도 대신 재현율)에 맞춰 마커 개수 점수(0~4)로 설계. 모든 마커는 as-of 안전(lookahead 없음) — 특히 저점 높이기는 과거 저점만 비교. 필수 지표 컬럼이 없으면 빈 신호를 반환(조용한 오작동 방지).
2. **신호 해석 정보 동봉**: `TurnaroundSignal`은 마커 내역·`confirmed`(supertrend가 이미 추세 on인지)·`stop_level`/`stop_pct`(직전 스윙 저점 기반 손절)·`is_candidate`(점수≥2 AND 약세 맥락)를 담는다. 약세 맥락(최근 20일 중 50일선 아래) 조건으로 "상승추세 중 눌림"이 아니라 "하락에서의 반등"만 후보로 거른다.
3. **check 출력 배선** (`src/pipelines/quick_check.py`): `run()`이 `raw_dataframe`로 신호를 계산해 결과 dict에 넣고, `format_output()`이 score>0일 때 "### 턴어라운드 신호" 한 줄을 렌더. 공용 변환 헬퍼 `_turnaround_dict()`.
4. **screener 발굴 모드** (`src/pipelines/screener.py`, `src/tools/screener/{evidence,models}.py`, `src/cli/main.py`): `ScreenerEvidence`에 턴어라운드 필드 추가, `_collect_one()`이 이미 계산한 6개월 df로 신호 산출(중복 fetch 없음). 파이프라인이 후보를 마커수→총점 순으로 모아 "턴어라운드 발굴 후보" 표로 출력. `jarvis screen --turnaround`는 리더 표를 생략하고 발굴에 집중.
5. **brief 배선** (`src/pipelines/brief.py`, `src/tools/brief/{models,render}.py`): `BriefItem.turnaround`(요약 문자열, score>0일 때만) 추가, 종목 상세의 기술 Verdict 다음에 렌더.
6. **예측 아님 명시**: 코어 docstring, `screen` 발굴 표 헤더("예측 신호 아님. 후보 표면화용 — 기사·시장 상황은 직접 판단하세요."), CLI 옵션 설명에 성격을 박아 오해를 방지.
7. **테스트 14개**: 마커별 결정론적 합성 df 검증 + IndicatorCalculator 컬럼 호환 + 3표면 렌더링. 전체 1305 passed.

## Before / After

```
Before (jarvis check HOOD):
  ### Technical Verdict
  - Action: add (pullback_add, ...)
  ### 최근 점수 추이 ...

After (jarvis check HOOD):
  ### Technical Verdict
  - Action: add (pullback_add, ...)
  ### 턴어라운드 신호
  - 턴어라운드 3/4 · [20/50일선 재탈환 · 거래량 수반 양봉 · 저점 높이기] · check 확인됨(추세 on) · 손절 91(-11.8%) · ★후보
  ### 최근 점수 추이 ...
```

```
Before: jarvis screen  → 테마 + 주도주 TOP50 표만
After:  jarvis screen  → 위 + "턴어라운드 발굴 후보" 표
        jarvis screen --turnaround → 발굴 후보 표에 집중(리더 표 생략)
```

## Impact

- CLI 출력 변화: `check`·`brief`에 턴어라운드 한 줄(신호 있을 때만), `screen`에 발굴 후보 표 추가.
- 신규 CLI 옵션: `jarvis screen --turnaround`.
- 환경변수·마이그레이션 없음. 기존 스코어링/판정 로직 불변(추가만).

## Constraints

- **예측 알파를 의도적으로 주장하지 않음**: 백테스트상 나이브 기준선 미통과, check 확인 분리는 대부분 기계적 상관(확인 이후 10→20일 우위 +0.7% vs +0.2%)임을 확인. 최종 매매 판단(기사·시장 상황)은 사용자 몫.
- **자동 오버레이 제외**: 시장 레짐(지수 200일선) 필터도 우위를 못 줘 트리거에 넣지 않음.
- **마커 가중치·임계값 튜닝 보류**: 현재 동일 가중 점수(threshold=2, 상수 분리). 실사용 후 조정 여지.
- 파생 보류 항목(ROADMAP): Task 13 저항 인식 패널티, Task 14 구조 점수(higher-low).

## Related

- 설계/검증: `docs/superpowers/specs/2026-08-24-bottom-watch-design.md` (bottom_watch 폐기·검증 기록)
- 결정 이력: `docs/worklog/bottom-watch-signal.md`, `docs/ROADMAP.md` Task 15
- ADR: 없음
- FEATURES.md: §11 턴어라운드 신호 추가
- 후속: change record PR 번호 반영, 마커/임계값 실사용 튜닝
