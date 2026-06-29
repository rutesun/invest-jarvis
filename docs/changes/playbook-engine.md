# Change Record: Playbook 엔진 + analyze 통합

**Status**: Merged
**Date**: 2026-06-12
**PRs**: #40 (claude/pedantic-edison-17e120)
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

`jarvis analyze` 결과에 매수·매도 판단 근거가 없었다. 기술적 지표 수치는 나오지만 "지금
진입 가능한가", "어디서 손절하나"를 판정하는 정량 기준이 없어 해석을 전적으로 사용자에게
맡겼다. 시장 환경·업종 강도·상대강도·매집 상태·피벗 돌파를 각각 독립 게이트로 체계화하고,
통과 시 포지션 사이징까지 산출하는 Playbook 엔진을 신규로 구축한다.

## What

1. **veto 게이트 레이어 (`gate.py`)**: A(시장환경)·B(Stage2)·C(RS강세)·E(VCP피벗) 4개가
   하나라도 실패하면 진입 불가. D(매집)·I(CAN SLIM 복합)·수급은 통과 후 가점.
   품질등급(A/B/C)과 Stage2 근접도(`N/7, 미충족 조건명`)를 CLI에 노출해 6/7 부분충족과
   0/7 구조적 약세를 진단 단계에서 구분할 수 있게 했다.

2. **순수 함수 모듈 분리 (`src/tools/playbook/`)**: 각 게이트 로직을 독립 모듈로 분리.
   - `market_regime.py` — 지수(`^GSPC`/`^KS11`/`^KQ11`) SMA200 방향으로 매수 환경 판정
   - `relative_strength.py` — 맨스필드 RS 0-100 정규화 + 4주 기울기. RSI와 다른 지표임.
   - `sector_strength.py` — 미국: FMP API 업종 퍼포먼스, 한국: KIS 업종지수 두 경로
   - `accumulation.py` — 오닐식 매집일(`up_vol > avg_vol × 1.5`)·분산일 카운터, 14일 윈도우
   - `vcp.py` — 피벗 돌파 감지(전고점 +2% 이내 + 거래량 급증)
   - `canslim.py` — C(분기EPS YoY)·A(연간EPS CAGR)·I(RS 80이상 + 업종 상위) 직접 계산,
     N·S·L·M은 다른 모듈 결과를 참조해 7요소 종합
   - `sizing.py` — 손절가 3후보(−8%/2×ATR/구조적 지지) 중 최솟값 + 계좌 위험% → 주수/R
   - `exit_rules.py` — 추세 종료 5신호(SMA50 이탈·RS 반전·거래량 감소·8% 룰·21일선 종가)
   - `engine.py` — 위 모듈을 순서대로 실행해 `PlaybookVerdict` 반환
   - `holdings.py` — `playbook.yaml` 파싱 (계좌 위험% 설정, 보유 종목 목록)

3. **analyze 파이프라인 통합 (`deep_dive.py`)**: `PlaybookEngine`을 주입하고
   `apply_playbook_veto`로 `decision_summary`를 후처리. 기존 기술적 분석 흐름은 불변,
   Playbook 결과가 마지막에 붙는 구조.

4. **CLI 출력 (`main.py`)**: `_format_playbook_section()` 추가. 게이트 체크리스트 +
   CAN SLIM 7요소 상세(`C: 분기EPS YoY 981.8%` 수준) + 포지션 플랜을 "📋 플레이북 평가"
   섹션으로 렌더링. EPS 분기/연간 추이도 추가 노출.

5. **EPS CAGR 크래시 수정 (`deep_dive.py`)**: 적자→흑자 전환 종목(예: COHR)에서
   `(oldest<0, newest>0)^(1/n)` → Python 복소수 → Pydantic `float | None` 검증 오류로
   전체 analyze가 죽던 문제. `_compute_eps_cagr()` 순수 함수로 추출, sign change 시
   `None` 반환. 경계 케이스 4종(both-positive, sign-change, zero, n=0) 테스트 커버.

6. **Stage2 조건 메트릭 노출 (`minervini.py`)**: 기존에는 `is_stage2: 0.0/1.0`만 반환.
   개별 조건 `cond_close_gt_ma50` 등 7개 + `STAGE2_CONDITION_LABELS` 상수 추가로
   gate.py가 미충족 조건명을 CLI에 직접 표시할 수 있게 했다.

## Before / After

```
Before (jarvis analyze AAPL):
  기술적 분석 요약
  펀더멘털 요약
  종합 의견: 매수 검토 가능
  (진입 조건, 손절가, 포지션 크기 없음)

After:
  기술적 분석 요약
  펀더멘털 요약
  📋 플레이북 평가
    게이트: ✅ A(시장환경) ✅ B(Stage2: 6/7) ✅ C(RS: 82.3) ❌ E(VCP 미돌파)
    → 진입 불가 (게이트 E veto)
    CAN SLIM: C✅ A✅ N✅ S❌ L✅ I✅ M✅ (6/7)
      - ❌ S: 거래량 1.01x 평균, 돌파 조건 미충족
    포지션 플랜: 피벗 돌파 확인 후 재평가
```

```
Before (EPS CAGR, COHR 같은 적자→흑자 전환 종목):
  eps_cagr = (newest / oldest) ** (1 / n_years) - 1
  # oldest=-3, newest=1 → (-3)^0.5 → complex → Pydantic crash

After:
  def _compute_eps_cagr(newest, oldest, n_years):
      if oldest == 0 or newest / oldest <= 0:
          return None   # sign change → undefined
      return (newest / oldest) ** (1.0 / n_years) - 1
```

```
Before (Stage2 veto 메시지):
  ❌ B (필수): is_stage2=0.0

After:
  ❌ B (필수): is_stage2=0.0 (6/7, 미충족: 종가>50일선)
```

## Impact

`jarvis analyze {ticker}` 출력 끝에 "📋 플레이북 평가" 섹션이 추가된다. 게이트별 veto 여부,
CAN SLIM 7요소 상세, 포지션 사이징 계획이 포함된다.

`FMP_API_KEY` 미설정 시 미국 종목의 업종 강도(`sector_strength`)가 `None`으로 처리된다
(graceful degradation). 한국 종목은 KIS 업종지수 경로를 사용한다.

보유 종목 추적이 필요하면 프로젝트 루트에 `playbook.yaml`을 작성한다(`holdings.py` 참조).

## Constraints

- **sector_strength graceful degradation**: `FMP_API_KEY` 미설정 시 미국 종목의 업종 강도는
  `None` 처리, gate D를 중립으로 다룬다. 키 없다고 전체 analyze가 실패하면 안 된다.
  한국 종목은 KIS 업종지수 경로로 분기해 FMP 없이도 동작한다.
- **veto는 binary**: 게이트 통과 여부는 binary veto. 부분 점수로 veto를 희석하지 않는다.
  6/7 Stage2 충족 종목도 veto 결과는 "불가"이며, 근접도는 진단 정보로만 노출한다.
- **holdings.yaml 선택사항**: `playbook.yaml`이 없어도 analyze는 정상 동작.
  포지션 사이징은 기본 위험% 2%를 사용한다.
- **CAN SLIM N·S·L·M 직접 계산 미구현**: N(신고가 신제품)·S(공급)는 정량화 난이도상 참조값
  위임. 규칙상 추후 보강 가능한 구조는 잡혀있음.

## Related

- 설계: `docs/superpowers/specs/2026-06-10-playbook-engine-design.md`
- 계획: `docs/superpowers/plans/2026-06-10-playbook-plan{1~9}-*.md` (plan1: KIS 데이터,
  plan2: EPS, plan3: 매집, plan4: RS, plan5: 업종, plan6: regime·Stage2·VCP,
  plan7: CAN SLIM, plan8: engine, plan9: wiring)
- ADR: 없음
- FEATURES.md: Playbook 엔진 섹션 추가 필요
