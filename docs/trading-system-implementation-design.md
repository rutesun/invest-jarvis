# 단계형 모멘텀 매매 시스템 — 구현 설계

> 개념·방법론은 [trading-system-materials-recipes-design.md](trading-system-materials-recipes-design.md) 참조. 이 문서는 그 개념을 실제 jarvis 코드에 어떻게 앉힐지의 구현 설계다. 독립 리뷰의 지적(사전 등록·대조군·gate→knob·look-ahead·표본 비독립)을 반영했다.

## 0. 요약

- **재료(Features)**는 기존 `src/tools/technical/`을 거의 그대로 재사용한다(지표·컴포넌트·컨텍스트).
- **레시피(Strategy)**는 기존 `aggregator.py`/`shadow_v2.py`의 액션 결정권을 걷어내고, **설정(config)으로 정의되는 레시피 레지스트리**로 재작성한다. 대가 전략은 named 레시피가 된다.
- **상태(State)**와 **백테스트**는 신규다. 기존 stateless 조언 파이프라인(quick_check/deep_dive)은 건드리지 않는다.
- "작게 잃고 크게 먹기"는 진입이 아니라 **사이징·추가·청산**에서 나오므로, 청산을 세 개의 경쟁 레시피(Weinstein/Minervini/O'Neil)로 두고 백테스트로 고른다.

## 1. 3층 매핑: 개념 → 실제 코드

### 1.1 재료 (Features) — 대부분 재사용

| 개념 | 기존 코드 | 판정 |
|---|---|---|
| 순수 지표 (SMA/ATR/RSI/거래량/고저/이격도/Supertrend) | `technical/indicators.py`, `context.py` | 그대로 재사용 |
| Stage(정배열) | `components/minervini.py` | 재사용, 단 **관문 아닌 손잡이로** |
| VCP / breakout / 캔들 | `components/patterns.py` | 재사용, threshold를 손잡이로 |
| 거래량 확장/Pocket Pivot/Power Gap | `components/volume.py` | 재사용, threshold를 손잡이로 |
| 다이버전스 | `components/divergence.py` | 재사용 |
| cRSI Hook/Squeeze | `components/crsi.py` | 재사용 |
| 속도(기울기/가속) | `components/velocity.py` | 재사용 |
| 지지·저항 confluence | `components/risk.py` | 재사용 |
| 바닥 구조(초기 반등) | `bottoming.py` | 재사용, threshold를 손잡이로 |
| 8컴포넌트 오케스트레이션 | `scorer.py` | 재사용 |

핵심 원칙(리뷰 반영): **"재료라고 검증 면제 아님."** minervini의 Stage 조건, patterns의 VCP 임계값, bottoming의 lookback 등은 이미 가정이 든 **복합 재료**다. 이 숫자들은 전부 레시피가 참조하는 **파라미터(손잡이)**로 노출하고, 백테스트 검증 대상에 포함한다. 특히 "Stage 2 아니면 무조건 탈락" 같은 하드 게이트는 금지하고, Stage도 레시피가 켜고 끌 수 있는 조건으로 둔다.

### 1.2 레시피 (Strategy) — 재작성

현재 `aggregator.py`(adjusted_score = "A")와 `shadow_v2.py`("A′")가 재료를 합산·게이트해 액션을 정한다. 이 둘은 **레시피의 원형**이지만 두 가지가 문제다: (a) 상수가 하드코딩돼 실험이 어렵고, (b) 액션 결정권을 코드가 쥐고 있어 "레시피 갈아끼우기"가 안 된다.

재작성 방향:
- 액션 결정권을 코드에서 떼어 **레시피 config**로 옮긴다. 레시피 = `선택 + 관문/점수 + 비중/문턱 + 매도·사이징`.
- `aggregator`/`shadow_v2`의 계산 로직 자체(점수 vs 게이트 분리 등)는 좋은 자산이므로 레시피 실행기의 내부 구현으로 흡수한다.

**레시피는 두 층으로 구성한다 (블록 + preset).** 작가별 통짜 파일로 두지 않는다 — 그러면 무엇이 성과를 만들었는지 분리 못 하고(진입 vs 청산), 중복이 생기고, 섞어보기가 안 된다. 삼성전기 사례가 "진입과 청산은 분리되는 문제이고 조합이 결과를 가른다"를 실증했다.
- **블록(기능별, 조합 가능)**: `entry.py`/`exit.py`/`sizing.py`에 여러 블록을 두고 각 블록에 출처 태그를 단다. 예) 진입 vcp_breakout[M]·cup_handle[O]·stage2[W]·sma50_reclaim[ours]; 청산 profit_target[O]·staged_risklevel[M·기존A]·wide_trail_ma[W]; 사이징 pyramid[O]·r_fixed_probe_core[M·ours].
- **preset(대가별 조합)**: `presets.py`에서 블록을 끼워 이름 붙인 조합. `ONEIL`/`MINERVINI`/`WEINSTEIN`/`OURS_A`(기존 A/A′) + 실험용 `MIX`(예: 미네르비니 진입 + 와인스타인 청산).
- **탐색 규율**: 조합은 경우의 수가 폭발하므로 시도 예산(§4.4)과 짝짓는다. 대가 preset을 출발점으로, **한 번에 한 축만 바꿔** 비교한다(예: 미네르비니 고정 후 청산만 W/M/O). 전조합 브루트포스 금지.

### 1.3 상태 (State) — 신규

현재 시스템에는 상태기계가 없다(전부 stateless 스냅샷). 신규로 만든다.

```text
WatchState  (미보유):  IGNORE → WATCH → ARMED → ENTRY_CANDIDATE
PositionState(보유):  FLAT → PROBE → CORE → FULL
ManagementMode:       NORMAL / WINNER
RiskLevel:            0..4   (청산 레시피가 사용)
```

## 2. 재사용 / 수정 / 신규 판정

| 구분 | 대상 | 조치 |
|---|---|---|
| 그대로 재사용 | `indicators.py`, `context.py`, `scorer.py`, `components/*`(대부분) | 재료 계층으로 그대로 사용 |
| 수정(파라미터화) | `patterns.py`·`volume.py`·`bottoming.py`·`minervini.py`의 하드코딩 임계값 | 손잡이로 노출 |
| 재작성 | `aggregator.py`·`shadow_v2.py`의 액션 결정 로직 | config 기반 레시피 실행기로 이전 |
| 신규 | 상태기계, 사이징·추가·청산 레시피, 백테스트 하니스, 데이터 영속 캐시, 유니버스 | 아래 §3 |
| 손대지 않음 | `pipelines/quick_check.py`, `deep_dive.py`, `brief`, CLI 기존 커맨드 | 그대로 |

데이터 계층(조사 결과):
- 재사용 가능: yfinance(미국 전체 기간, 자동 수정주가), KIS(한국 최대 3년, 수정주가), 지수 프로바이더.
- 부족 → 신규 필요: (a) 한국 3년 초과 구간, (b) 상장폐지 종목/시점정합 유니버스, (c) 가격 영속 캐시(Parquet/SQLite). 초기 백테스트는 최근 3년 + 고정 티커 리스트로 시작하고, 유니버스·상폐는 확장 과제로 명시(생존편향은 §4.4에서 `log`로 표면화).

## 3. 코드 구조

기존 조언 파이프라인과 성격(stateful)이 달라 별도 최상위 패키지로 분리한다. 재료 계층만 공유한다.

읽는 법: **tools=재료(숫자 뽑기), research=판단·기억·실행, backtest=채점, pipelines=기존 제품.** 데이터는 재료→판단→검증으로 흐르고, 검증 통과분만 나중에 pipelines에 얹는다. (재료 준비(serving/pivots)는 research가 아니라 재료 계층에 둔다 — features/ 아래 두지 않는다.)

```text
src/
  tools/technical/            # ① 재료: 차트에서 숫자 뽑기
    indicators.py             #   (기존) SMA·RSI·ATR·거래량
    components/               #   (기존) VCP·돌파·Stage 신호
    context.py                #   (기존) 추세/과열/거리
    serving.py                #   (신규) 오늘까지의 봉만 시점정확히 내보내기 (look-ahead 차단)
    pivots.py                 #   (신규) 확정 지연(lag) 반영 고점·저점 (§4.5)
  research/                   # ② 판단·기억·실행 (레시피+상태+실행)
    recipes/                  #   전략 = 블록(기능별) + preset(대가별 조합)
      entry.py                #     진입 블록들(출처 태그): vcp[M]·cup_handle[O]·stage2[W]·sma50_reclaim[ours]·20d
      exit.py                 #     청산 블록들: profit_target[O]·staged_risklevel[M·기존A]·wide_trail_ma[W]
      sizing.py               #     사이징 블록들: pyramid[O]·r_fixed_probe_core[M·ours]
      presets.py              #     이름 붙은 조합: ONEIL/MINERVINI/WEINSTEIN/OURS_A + 실험용 MIX
      registry.py             #     블록·조합 목록 + 출처·원칙·손잡이 메타
    states.py                 #   WatchState/PositionState/Mode/RiskLevel + 전이
    execution.py              #   t종가 신호 → t+1시가 집행, 갭 처리
    market_profile.py         #   KR/US 거래비용·세금·상하한가·틱 (실행 규칙)
    engine.py                 #   day-stepper 오케스트레이터(순수 결정 함수)
  backtest/                   # ③ 검증 하니스
    runner.py                 #   walk-forward, 홀드아웃 잠금, 시도 수 기록
    metrics.py                #   R분포·payoff비·기댓값·꼬리·블록 부트스트랩
    controls.py               #   대조군: buy&hold, 랜덤진입+동일청산
    universe.py               #   유니버스(초기 고정 리스트) + 생존편향 로그
    datastore.py              #   가격 영속 캐시(Parquet)
  pipelines/                  # ④ 기존 제품 — 안 건드림 (quick_check/deep_dive/brief)
  cli/main.py                 #   (기존) + research/backtest 커맨드 추가
tests/
  fixtures/technical/scoring/ # (기존) 골든 재사용: BE/NVDA/LULU/PANW/005930
  backtest/                   # (신규) 골든 케이스 + 사전등록 로그
```

엔진 규약: 입력 "t까지의 봉 + 현재 상태", 출력 "t+1 집행안 + 다음 상태". I/O는 밖에서 주입 → 백테스트와 실운영이 같은 엔진 공유. **전체 시리즈 선계산 후 슬라이스 금지**(look-ahead 누수 방지) — 매 스텝 t까지의 데이터로만 재료를 계산한다.

## 4. 백테스트 설계

### 4.1 무엇을 측정하나 = 레시피
재료는 고정, **레시피만 갈아끼워** 비교한다. 진입 레시피, 사이징/추가 레시피, 청산 레시피 각각을 후보로 둔다.

### 4.2 지표 (비대칭을 보이게)
평균수익률이 아니라 **손익 분포**를 본다: 승률, 평균이익÷평균손실(payoff), R 기댓값, 최대낙폭, 그리고 **꼬리 모양(소수 거래가 수익 대부분을 만드는가)**. 라벨은 옵션 B(고정 기본 청산 포함 미니 시뮬 → R 분포).

### 4.3 청산 레시피 실험 — "크게 먹기"의 핵심
같은 진입/사이징 위에서 세 청산을 붙여 비교한다.

```text
레시피 W (Weinstein):  넓은 추적 손절(장기 MA, 100/150/200일 손잡이) — 큰 꼬리 극대화
레시피 M (Minervini):  단계 축소(기존 RiskLevel 0..4) — 드로다운 축소, 꼬리 일부 희생
레시피 O (O'Neil):     목표 익절(20~25%) + 급등 리더 예외 보유
```
대가 합의(모두 채택): 짧은 손절, 이익 쿠션 있을 때만 추가, 피벗에서 멀면 추격 금지, 시장/추세 방향 우선.

### 4.4 가드레일 (사전 등록 = 실험 전 숫자로 확정)
- 총 백테스트 시도 예산(상한)과 홀드아웃 개봉 조건·실패 시 처리를 **결과 보기 전에** 못박는다.
- 대조군: buy&hold, 랜덤진입+동일청산(진입의 공을 청산과 분리).
- 표본 비독립성: R은 국면에 몰리므로 **블록/국면 클러스터 부트스트랩**으로 추정.
- 거래비용/슬리피지/갭을 MarketProfile로 반영(한국 거래세·상하한가 포함).
- 유니버스 축소·상폐 미포함 등 커버리지 한계는 `log`로 표면화(침묵 금지).

### 4.5 look-ahead 처리
- pivot은 미래 봉이 있어야 확정 → `pivots.py`에서 **확정 지연(예: +N봉)**을 명시하고 이벤트 시점을 지연 반영.
- 수정주가 소급 조정 주의: 매 스텝 t까지 정보로만 계산(전체 선계산 금지).
- t종가 신호 → t+1 시가 집행, 갭은 R에 반영.

### 4.6 골든 케이스 (티커별 정답)

조사로 확인된 기존 자산과 사용자 예시 티커를 정답 케이스로 쓴다.

| 티커 | 시장 | 데이터 | 정답(ground-truth) | 검증 성격 |
|---|---|---|---|---|
| BE | US | fixtures 장기(2025-01~2026-09) + tmp | 바닥형성 8/3~9/2 `accumulate` → 9/4 SMA50 재탈환 `buy` | 초기 반등 진입(가장 완성) |
| 005930 삼성전자 | KR | fixture 2026-06~07 + 저널 | 6/23 `buy`(20일선 지지+거래량) / 7/02 `avoid·reduce`(추세이탈) / 7/14 재진입 | 추세이탈 회피 + 재진입 |
| 009150 삼성전기 | KR | tmp OHLCV + 저널 | 7/08 50일선 이탈 매도, 7/14 100일선 반등 재진입 | 청산·재진입 (정답 주석 필요) |
| HOOD | US | tmp OHLCV만 | **없음 — 사용자가 "언제 샀어야" 정의 필요** | 사용자 예시(주석 대기) |
| PANW | US | fixture | 4월말 풀백 `add`(pullback_add) | 추가매수 타이밍 |
| NVDA | US | fixture | 강세 국면 `buy/add/hold` 유지, 바닥가점 금지 | false bottom 억제 |
| LULU | US | fixture | lower-low 하락 `reduce/avoid` 유지 | false bottom 억제 |

주의: 기존 fixture의 정답은 "기술적 판정(action)"에 대한 회귀 규약이지 "실제 매매 R"이 아니다. 백테스트 골든은 여기에 더해 **진입→청산 전체 경로의 R**을 고정해야 한다. HOOD·삼성전기는 사용자의 원래 예시이므로, "이 시점에 샀으면 좋겠다"는 정답을 주석으로 확정해야 골든으로 승격된다.

## 5. 빌드 순서

```text
0. 사전 등록 문서 작성 (시도 예산·홀드아웃 규칙·대조군·부트스트랩·비용) — §4.4
1. features/ 어댑터 + pivots 확정지연 + MarketProfile, datastore(Parquet 캐시)
2. backtest runner(walk-forward/홀드아웃) + metrics(R분포·부트스트랩) + controls
3. 고표본 단순 트리거(20D 돌파/SMA50 회복/타이트 pullback)로 harness 정직성 검증
   - 골든: BE, 005930, PANW, NVDA, LULU로 회귀 고정
4. 진입 레시피 확장(VCP/베이스 등 복합 재료를 손잡이로)
5. 사이징/추가 레시피(R고정·이익쿠션 후 추가)
6. 청산 레시피 W/M/O 비교 실험 (§4.3)
7. 홀드아웃 1회 개봉 → 채택 레시피 확정
8. 채택분만 deep_dive에 evidence로 연결(표시 우선, action 미덮어씀)
```

## 6. 열린 결정

1. 엔진 패키지 위치: `src/research/`(제안, 조언 파이프라인과 분리) vs `src/pipelines/backtest/`(기존 컨벤션 편입).
2. 상태 저장: 로컬 보유 파일 확장 vs SQLite.
3. HOOD·삼성전기 정답 주석: 사용자가 "이 시점 매수/매도" 기준을 확정해야 골든 승격.
4. 복합 재료 손잡이 개방 범위: 넓힐수록 과적합↑(시도 예산과 연동).
