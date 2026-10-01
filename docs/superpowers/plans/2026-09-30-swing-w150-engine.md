# SWING_W150 v3 엔진화 + jarvis 참고 표시 — 구현 계획

브랜치: `feature/swing-w150-engine` (base: main `cf8d564`)
기준 동작(정답): `src/backtest/universe_transition.simulate(f, T=False, D=True, X=None, exit150="2d1R", trim="x", arm_ext=0.40, trim_st=False, trim_frac=1.0, trim_ma="sma20")`

## 목표

1. 백테스트 스크립트의 v3 동작을 제품 코드(재료 → 레시피 → 상태)로 옮기고, 스크립트와 **같은 매매**를 내는지 골든 테스트로 고정한다.
2. `jarvis check`·`brief`에 SWING_W150 상태를 참고 정보로 표시한다. 기존 action·verdict·A′는 바꾸지 않는다.

범위 밖(YAGNI): 레시피 교체 구조, 추가매수·RiskLevel·WINNER, 섹터·베타 관문, 거래비용, 실제 보유 파일과의 연동.

## 원칙

재료(지표)는 `src/tools/technical` 한 곳에 두고 최대한 재사용한다. 재료를 해석하는 전략(규칙·상태 판정)은 `src/strategies/`에 두고, pipelines는 전략을 가져다 쓴다. 레이어: providers → tools → strategies → pipelines → cli.
재검증 결과(worklog 참고): 백테스트 자체 ATR·슈퍼트렌드를 jarvis `IndicatorCalculator`로 바꿔도 v3 성과가 같다(새 기간 370회 1.02R → 367회 1.02R). 그래서 재료는 jarvis 기준으로 통일한다.

## 파일 구조

```text
src/tools/technical/                 재료 (기존 + 부족분만 추가)
  indicators.py        (재사용) SMA 20/50/150/200, ATR(Wilder), SuperTrend_Dir, Vol_SMA_20
                       (추가)   SMA150 21일 기울기, SMA20 5일 기울기, 직전 50·20일 고가, 20일 저가
  pivots.py            (신규)   확정 저점·고점(3일 지연) → 저점 상승, 저점·고점 동시 하락
                                기존 Swing_High/Low·swing_extractor는 중심 창(미래 봉 사용)이라 재사용 불가

src/strategies/swing_w150/           전략 = 재료 해석 (규칙 + 상태). tools만 import
  __init__.py
  rules.py             S/D 진입 조건, 구조 붕괴, 초기 손절, 졸업, 2일/−1R 청산, 과열 매도·재매수
  engine.py            replay(df) → 매매 목록 / current_state(df) → 오늘 상태
  models.py            SwingTrade, SwingState (+ summary_line: check·brief 공용 한 줄)

src/pipelines/quick_check.py         (수정) 이미 받은 가격 데이터로 engine 호출 → 섹션 추가
src/pipelines/brief.py               (수정) 같은 방식으로 호출 → BriefItem에 담기
src/tools/brief/models.py·render.py  (수정) 필드 1개, 줄 1개. 폴더 이동은 별도 PR

tests/fixtures/swing_w150/
  <TICKER>.csv         원본 OHLCV(수정주가, 2014~)
  <TICKER>.trades.json 정답지 = 기준 simulate(jarvis 지표 교체판)의 매매 목록
  generate.py          정답지 재생성 스크립트 (테스트 중 실행 안 함)
tests/tools/technical/test_pivots.py        확정 지연(미래 봉 미사용) 경계
tests/strategies/swing_w150/test_golden.py   엔진 매매 == 정답지
tests/strategies/swing_w150/test_state.py    대상아님/대기/신호/보유 판정
tests/harness/                              정답지 형식 contract 함수
```

`tools/technical/tool.py`·기존 판정(aggregator/shadow_v2)은 수정하지 않는다. `src/backtest/` 기존 스크립트도 수정하지 않는다.

## 2단계: 엔진화

### 2-1. 정답지 고정 (먼저)
- 종목 4~5개: S 매매, D 매매, 손절, 150일선 청산, 과열 매도→재매수가 최소 1건씩 포함되도록 고른다.
- 정답 생성은 `universe_jarvis_indicators.prepare_jarvis` + 기준 `simulate`(v3 설정). 데이터는 자르지 않는다(워밍업 250봉, 경로 의존).

### 2-2. 재료 추가 (`tools/technical`)
- 추가 컬럼은 `IndicatorCalculator`에 넣되 기존 컬럼 값은 바꾸지 않는다(기존 check 회귀 테스트로 확인).
- `pivots.py`는 백테스트 `confirmed_pivots`와 같은 결과를 내는지 단위 테스트로 고정.

### 2-3. 규칙 + 상태 (`strategies/swing_w150`)
- `replay(df)`: 기준 simulate의 v3 경로만 남긴 동일 루프. t=250부터, 종목당 한 포지션, t 종가 신호 → t+1 시가 진입, 장중 저가 ≤ 손절이면 손절가 체결, 청산은 종가.
- `current_state(df)`:
  - 보유: 마지막 매매가 아직 열려 있음. 진입일·진입가·손절·1R·현재 R·졸업 여부·과열 무장·과열 매도 후 재매수 대기.
  - 신호: 마지막 봉에서 S 또는 D 트리거(내일 시가 진입). 예상 손절은 마지막 종가로 근사.
  - 대기: 트리거 전제만 충족(S: 종가 > 상승 150일선 / D: 바닥 조건). 돌파 기준가와 거래량 조건 표시.
  - 대상아님: 그 외.
- 대기 판정은 기준 스크립트에 없는 표시용 로직 → 골든 대상 아님, 단위 테스트로 고정.

### 2-4. 골든 테스트
- 건수, kind, entry_date, exit_date, why, entry/exit·R(≈1e-9)가 정답지와 같아야 한다.

## 3단계: jarvis 연동 (표시 우선)

- pipeline이 `tech.raw_dataframe`(이미 받은 3년치)로 `current_state`를 호출한다. 실패 시 None + `logger.warning`(조용히 삼키지 않음).
- `quick_check.format_output`에 섹션 추가:
  ```text
  ### SWING_W150 (백테스트 시스템 · 참고)
  - 상태: 대기 (S 경로)  — 돌파 기준 152.30 / 거래량 20일 평균 1.4배 이상
  - 예상 손절: 138.10 
  - ※ 미국 5년·10년 백테스트 기준. 기존 판정과 별개인 참고 정보
  ```
  보유 상태면 "시스템 가상 진입 2026-08-14 @ 140.2 / 손절 128.0 / 현재 +1.8R / 과열 무장: 아니오".
- `brief`: `BriefItem.swing_w150` 필드 + render에 한 줄("SWING_W150: 신호 — 내일 시가 진입, 손절 ○○").
- action·verdict·bucket·bonus 계산에는 쓰지 않는다. 기존 브리프/체크 테스트가 그대로 통과하는지로 확인한다.

### 알려진 차이
- 제품은 3년치 데이터를 쓰므로 replay 시작점이 백테스트(2014~)와 다르다. 3년 창 앞에서 시작된 매매는 보지 못하고, 워밍업 250봉 뒤(약 2년치)만 replay된다. 현재 상태가 긴 데이터 기준과 다를 수 있다 → 표시 문구에 "최근 3년 기준" 명시, 골든은 긴 데이터로 고정.
- "보유"는 시스템의 가상 포지션이다. 사용자의 실제 보유 파일과 무관하다.

## 검증 순서
1. 골든 테스트 통과(엔진 == 기준 스크립트)
2. `uv run pytest` 전체 통과(기존 check/brief 회귀 없음)
3. 실데이터 실행: `uv run jarvis check NVDA 005930 …`, `uv run jarvis brief` 출력 확인
4. `/change-record` + `docs/FEATURES.md` 갱신 → PR

## 결정 사항
- 한국 종목도 미국과 똑같이 표시한다. 미검증 표기는 넣지 않는다(사용자 결정).
- CLAUDE.md·AGENTS.md 아키텍처 표에 Strategies 레이어 추가.
