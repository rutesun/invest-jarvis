# 설계 합의: 점수 vs 게이트 분리 (Claude ↔ codex, 2026-09-14)

사용자 질문: "차트 움직임·거래량·보조지표로만 점수를 매기고 minervini·supertrend는 게이트로
둬야 하나? minervini만?" → codex와 2라운드 토론, BE 실데이터 검증 후 합의.

## 합의안 (A′)
추세 레짐은 **게이트(자격/상한)**, 차트·거래량·모멘텀은 **점수(셋업 품질)**로 분리한다.

- **setup_score** = velocity + crsi + volume + patterns + divergence + risk-confluence (movement only).
- **regime gate** = Minervini 스테이지 사다리(weak / above50 / Stage2). 점수 기여 제거, 상태만 유지.
- **supertrend** = 방향(up/down)은 게이트, 매수전환 flip은 3거래일 TTL **트리거**(점수 가산 X).
- **bottoming** = additive bonus 폐기, **상태(bottoming_watch)**로. 점수 안 올리고 라벨만.

근거(핵심): Minervini Trend Template은 원설계가 매수 자격 필터(pass/fail)다 → ±40 가산은 오용.
BE에서 레짐 변화가 점수에 들어가 계단 점프 유발(9/2→9/3 minervini +45, 9/3→9/4 supertrend +65).
게이트는 action에 **상한(cap)**만 적용하고 점수를 올리지 않으므로, 점수는 매끄럽고 action은 확인
시점에만 승격(추세 확인 규율 유지).

## 액션 결정 매트릭스 (regime × ST × setup band)
setup 밴드: 강≥40 / 중 20~39 / 약 0~19 / 음 -25~-1 / 심각 <-25. 기본 new_entry_allowed=False.
선행 override(우선): 거래량 breakdown→avoid, fresh sell flip→reduce, overextended→hold+진입금지.

| Regime / ST | 강 ≥40 | 중 20~39 | 약 0~19 | 음 | 심각 |
|---|---|---|---|---|---|
| weak / any | accumulate\* | accumulate\* | accumulate\* | reduce | avoid |
| above50 / down | watch | watch | watch | reduce | avoid |
| above50 / up(+flip) | watch | watch | watch | reduce | avoid |
| Stage2 / down | watch | watch | watch | reduce | avoid |
| Stage2 / up | hold | hold | watch | reduce | avoid |
| Stage2 / up + fresh flip | **buy/add†** | hold | watch | reduce | avoid |

\* bottoming_watch=True면 accumulate, 아니면 watch. 음수 setup은 accumulate로 안 올림.
† 미보유=buy/보유=add — position은 technical 레이어에 없어 Playbook이 분기.

경계: weak+강setup=최대 accumulate / above50+ST down=최대 watch / buy는 Stage2+ST up+fresh flip+강setup에서만.

## bottoming 상태화 (SMA200 게이트 추가)
codex fixture 재계산: higher-low+volume-dry만이면 LULU 8일 오검출 → **+close_above_sma200**이면 LULU 0.
```
bottoming_watch = weak AND higher_low(10/30) AND volume_dry(5/20<0.85)
                  AND close_above_sma200 AND not volume_breakdown AND not fresh_sell_flip
```
momentum·divergence는 setup_score에만 두어 이중 계산 제거. SMA200 위 = 장기추세 유지 중 조정만 대상,
SMA200 아래 deep turnaround는 제외.
- 정리: accumulate action·entry_mode="bottoming_watch"·downstream 중립매핑 유지 /
  W_* 가중치·BONUS_MAX·bonus·BOTTOMING_CEILING·ACCUMULATE_FLOOR·bottoming_gradient_bonus 삭제 /
  테스트를 "점수+가산/상한"→"점수 불변+상태 라벨+진입금지"로 전환.

## 이행 경로 (밴드 재보정 불가피)
- **Ceiling-only PR은 점프 완화에 무효** — 점수에 minervini/ST가 남으면 raw 점프 그대로. Playbook이
  이미 Stage2를 게이트로 쓰므로(gate.py) technical hint 정합 정도의 안전값만 있음.
- **권장 PR1 = shadow**: setup_score/regime/st_state/buy_flip_age/bottoming_watch/action_v2를 병행
  계산·출력만. 기존 total_score/adjusted_score/action·raw 합계 계약(models.py) 불변 → 회귀 위험 낮음.
- **PR2 = cutover**: holdout 종목·국면으로 setup 밴드·hysteresis 재보정 후 action을 v2로 전환,
  legacy score는 한 릴리스 진단용 유지.
- 주의: 재보정 시 buy 밴드가 사실상 희소해짐(codex 계산: 223일 fixture에서 setup≥55 BE 10 / NVDA 9 /
  LULU 5일, ≥75는 0~2일). 시스템이 buy에 더 보수적으로 바뀜 — 의도적이나 사용자 확인 필요.

## 남은 불확실성(정직)
- setup_score도 velocity 때문에 여전히 출렁(BE 9/8→9/9 55→25). 게이트 분리는 의미 혼합만 고침 —
  score 변동성은 velocity의 event/state 추가 분리나 hysteresis가 별도로 필요.
- 전면 재보정 규모가 큼: 신설 레이어 + 매트릭스 + 밴드 재보정 + 골든 재베이스라인.

---

## Round 3 합의 (shadow 실측 반영): floor+ceiling 밴드 + 악화 사다리

shadow 실측이 두 결함을 드러냄: (1) 강세주 NVDA가 Stage2·ST up인데 움직임 setup 음수일 때
reduce/avoid로 오강등("음수 setup→레짐 무관 강등" 규칙이 과함), (2) setup 변동성(velocity).

**결정: 게이트를 [floor, ceiling] 밴드로.** setup은 밴드 안 위치만 정하고 risk override만 floor를 뚫는다.

| Regime / ST | Floor | Ceiling |
|---|---|---|
| weak / any | avoid | bottoming이면 accumulate, 아니면 watch |
| above50 / any | reduce | watch |
| Stage2 / down | reduce | watch |
| Stage2 / up (flip 없음) | hold | hold |
| Stage2 / up + fresh flip | hold | buy/add |

완성 매트릭스(밴드: 강≥40/중20~39/약0~19/음-25~-1/심각<-25):

| Regime / ST | 강 | 중 | 약 | 음 | 심각 |
|---|---|---|---|---|---|
| weak / any | accum./watch | accum./watch | accum./watch | reduce | avoid |
| above50 / any | watch | watch | watch | reduce | reduce |
| Stage2 / down | watch | watch | watch | reduce | reduce |
| Stage2 / up | hold | hold | hold | hold | hold |
| Stage2 / up + fresh flip | buy/add† | hold | hold | hold | hold |

† 미보유 buy/보유 add, 해당 셀만 new_entry_allowed=True. overextended면 hold/False.

**Stage2 floor=hold 안전장치 (가격 확인형 악화 사다리)** — 단일 bearish divergence로 floor를 뚫지 않음:
- Stage2/up + setup<0 + 종가<SMA20 2거래일 지속 → watch (조기 경고)
- 전일 Stage2 → 당일 weak(SMA50 이탈) → reduce (regime 재계산으로 자연 처리)
- fresh ST 매도 flip → reduce
- 거래량 동반 breakdown → avoid

**문제 2(setup 변동성)**: 전체 hysteresis는 보류(실신호 지연·flip TTL 충돌). 밴드 clamp가 대부분 흡수
(BE 35↔25는 같은 '중' band라 action 불변). demotion에만 SMA20 2일 확인. velocity event/state 분리는 후속.

**검증(합의)**: NVDA Stage2/up 9일 모두 hold(오강등 해소), BE 급점프 재발 없음, LULU buy/hold 0.
**남은 리스크(정직)**: 세 fixture엔 "Stage2 상승 후 본격 붕괴" 사례가 없어 floor 안전성 최종 증명 부족 →
Stage2 이탈/붕괴 holdout fixture로 회귀 고정 필요.

---

## Round 4 합의 (setup 변동성): A+B(상태/이벤트 분리) + bottoming 무효화 수정 + 비대칭 2-close

**원인(실측)**: setup 노이즈는 (1) velocity의 accel·turning-point 스태킹(±35), (2) 일회성 이벤트
컴포넌트(divergence·breakout·volume surge·cRSI Hook)를 매끄러운 품질 점수에 더하는 데서 옴.
velocity-only(A)는 BE만 개선(24.7→~15), NVDA는 무효(노이즈가 event 컴포넌트라).

**BE counterfactual (codex 재계산, 8/12~9/2, action 전이 횟수 / accumulate 일수)**:
| 처리 | 일일Δ | 전이 | accum일 |
|---|---:|---:|---:|
| 현행 | 22.7 | 8 | 7 |
| A: velocity 상태만 | 12.7 | 8 | 7 |
| A+B: 이벤트 제거 | 12.0 | 7 | 7 |
| +bottoming 무효화 수정 | 12.0 | 4 | 13 |
| +음수 2-close 강등 | 12.0 | **2** | **15** |

A-only는 8/18에서 오히려 악화(현행 5 → A -20): 부분 분리는 event mix가 남아 비일관 → **A+B 필수**.
C(EMA/decay)는 보류: B 이후 setup에 감쇠할 event가 없고 timing 지연만 추가.

**컴포넌트 상태/이벤트 분류(확정)** — setup_score엔 state만, event는 0점 trigger로 보존:
| 컴포넌트 | state (setup 유지) | trigger (setup 제외) |
|---|---|---|
| velocity | SMA20 기울기 방향 ±10 | 가속·피로·전환점 |
| cRSI | 밴드 위치 ±10, squeeze +5 | Hook Up/Down ±20 |
| volume | 없음 | Pocket Pivot·Tennis/Egg·Power Gap·surge |
| patterns | VCP +10/+20 | breakout·candlestick |
| divergence | 없음 | 모든 divergence |
| risk | 지지/저항 confluence ±10/15 | hard breakdown은 override |
- volume_dry는 bottoming_watch 전용(setup 가산 X — 이중계산 방지).

**weak churn 대응(B만으론 부족)**:
1. **bottoming_watch 무효화 버그 수정**: 현재 느슨한 is_breakdown(SMA20 아래+10일수익률 음수)까지
   bottoming을 꺼서 BE에서 16일 중 8일 깜빡임. → hard 조건(volume breakdown·매도flip·SMA200/구조
   상실)만 무효화로 좁힘 → accumulate 7→13일.
2. **비대칭 2-close 히스테리시스**: weak/above50에서 **score에 의한 하향 밴드 이동만** 2거래일 확인.
   상승 복귀·regime/ST 변경·hard override는 즉시 반영 → 전이 4→2, accumulate 13→15.
   대가: 저거래량 하락 경고 1일 지연 가능(단 매도flip·volume breakdown은 즉시 관통).

**주의**: state만 남기면 강 setup(≥40) 도달이 드물어짐(buy 희소화) → cutover 시 밴드 재보정 대상.

---

## Round 4 구현 결과 (shadow, 2026-09-14): 실측 검증

`shadow_v2.py`에 구현: setup_state_score(상태만)·bottoming 무효화 hard 조건화·확립된 약세 가드·
비대칭 2일 히스테리시스(apply_hysteresis). ARM은 갓 무너진 첫 다리의 가짜 accumulate가 나와서
`_established_weakness`(최근 10일 중 8일 SMA50 아래) 가드를 추가해 배제.

실측(fixture, action 전이 횟수 = 낮을수록 안정):
| 종목 | OLD 전이 | NEW 전이 | NEW 분포/비고 |
|---|---|---|---|
| BE(바닥) | 13 | **4** | accumulate 15일 안정(8/12~9/2), 9/3~4 reduce, 9/8~ hold. avoid→hold 급점프 소멸 |
| NVDA(강세) | 9 | **2** | Stage2 내내 hold, 눌림(above50)만 watch. 오강등 없음 |
| ARM(붕괴) | 5 | 7 | buy/hold/accumulate **0**(안전). watch/reduce/avoid 간 라벨 churn ↑ |
| LULU(하락) | 9 | 18 | buy/hold/accumulate **0**(안전). watch↔reduce churn ↑ |

- 핵심(보유·관찰) 사례 BE·NVDA는 크게 안정. 하락주는 방향은 안전(진입/보유/가짜바닥 0)하나 bearish
  라벨(watch/reduce/avoid) churn이 늘어남 — 비대칭 히스테리시스가 하락주 반등에 watch를 즉시 허용하기 때문.
- 후속(선택): 하락주(비 bottoming weak) churn을 줄이려면 weak 레짐에서 상·하향 모두 2일 확인(대칭)하거나
  watch/reduce 경계(0) 부근에 데드밴드. 보유/관찰엔 영향 없어 우선순위 낮음.
- 여전히 shadow(기존 action 불변). cutover 시 밴드·hysteresis 재보정.

---

## Round 5 합의 (cutover 전 호환성·유의미성·blocker)

### 이중게이트: 문제 없음(다른 레인)
- brief의 action/bucket authority = **playbook 게이트**(brief.py:120,123,145). technical verdict는
  **별도 hint**로만 전달·표시(brief.py:156, render.py:137). playbook B와 A′ regime은 같은
  minervini.is_stage2를 읽지만 **사실 공유일 뿐 authority 중복 아님**.
- 단, 표시를 계층화해야 함: `진입 자격: 부적격(Playbook B/C/E)` + `기술 상태: 바닥관찰(accumulate)`.
  "rejected+accumulate"는 모순 아니라 유용한 정보(진입 부적격 + 바닥 관찰).
- check의 "신규 진입 가능"은 오해 소지 → `기술적 타이밍 후보`로 문구 변경.
- **analyze는 예외**: action_v2를 factor 점수로 직접 매핑하면 Stage2가 간접 재가중됨.
  → action 매핑 대신 **setup_band + trigger로 factor 구성**, action_v2는 라벨로만.

### 유의미성: 의미 있으나 미완
- shipped(velocity/risk): BE 9/2 −80→−35, 9/3 avoid→reduce 착시 해소 = 유의미한 국소 개선.
  단 legacy aggregator는 여전히 전 컴포넌트 합산 → 9/3→9/4 Supertrend +65 additive 점프는 잔존.
- shadow A′: BE 전이 13→4, NVDA 13→2(hold 21일)로 핵심 개선. ARM/LULU는 bearish churn 악화.
  방향은 옳으나 cutover-ready 아님.

### cutover 최대 blocker: 밴드 미보정(buy = dead branch)
- 4종목 2026 YTD 688일에서 state setup 범위 −25~35, SETUP_STRONG=40 도달 **0일**,
  Stage2/up/fresh-flip 24 candidate-day에서도 buy **0회**. X=40은 죽은 가지 → **calibration 전 buy cutover 금지**.

### 기타 부족분
- regression이 apply_hysteresis를 호출 안 함 → 전이 횟수·no-lookahead·history parity 미고정.
- hysteresis가 raw setup_score를 effective로 덮음 → raw/effective 두 필드 분리 필요.
- TechnicalResult에 A′ contract(typed shadow) 없음.
- v2 action에 legacy reasons/adjusted history를 붙이면 설명 모순.
- analyze가 playbook 실패를 삼킴(deep_dive.py:284) → veto 누락 가능.

### 합의된 최소 cutover 순서
1. TechnicalResult에 typed shadow(raw/effective setup·regime·trigger·v2 verdict/history) 추가.
2. regression으로 정확한 전이수·no-lookahead·history parity 고정.
3. 30~50 US/KR·2~3년, 시간+종목 holdout으로 strong threshold {15,20,25,30} sweep.
4. buy는 날짜가 아닌 flip 에피소드 단위로 10/20일 초과수익·MFE/MAE 평가.
5. calibration 후 **brief 표시 + check 먼저 전환**(bucket/playbook은 그대로).
6. analyze는 action 매핑 대신 setup/trigger factor로.
7. legacy score/action/trace는 한 릴리스 동안 진단용 유지.

---

## 밴드 재보정 (2026-09-14, 옵션 A 실행)

39종목(US 30 + KR 8 + BE)×2024-01~2026-09 일봉으로 setup_state 분포·forward return 실측.

**진단**: state setup 분포 95%≤20, 최대 40. buy 후보(Stage2+up+fresh flip, n=272) 중앙값 0·최대 30
→ 기존 SETUP_STRONG=40은 buy가 절대 안 나오는 dead branch.

**buy 후보 20일 forward return (setup 구간별)**: 음<0 −2.3% / 약0~9 +6.4%(중앙값 −1.3%) /
**중10~19 +7.3%(중앙값 +1.7%)** / 강≥20 +6.6%(n=8, 희소). → buy 임계 setup≥10에서 forward 우위·음수 배제.

**결정**: SETUP_STRONG 40→**10**, MID 20→5. WEAK=0·NEGATIVE=-25 유지(음/심각은 forward 변별 약함, 리스크용).

**검증(전 유니버스, STRONG=10)**:
- buy 신호 101회(종목당 연 ~1.0회). forward 20일 평균 **+7.2%**/승률 54% vs 무작위 +2.7%/52% → 집계 우위.
- BE/NVDA 재보정 후에도 안정(BE 전이 4·accumulate 15일, NVDA Stage2 hold 유지).
- ⚠️ **홀드아웃 불일치**: 앞18종목 buy +13.3%(62%) vs 뒤21종목 −1.5%(43%). buy의 out-of-sample
  일관성은 약함 → buy는 **hint로만**(playbook이 진입 authority). 표준 alpha로 과신 금지.

**남은 것**: 종목/시간 무작위 홀드아웃·flip 에피소드 MFE/MAE 심화는 후속. 현 재보정은 "buy dead branch
해소 + 집계 우위" 수준으로 충분. cutover 시 STRONG은 이 값에서 시작해 실사용 관찰로 미세조정.

---

## Round 6 합의 (PANW 초기돌파 미검출 수정 → H′)

사용자 PANW 테스트로 결함 발견: A′가 recovery breakout(167→243)을 내내 watch로 놓침. 원인:
(1) regime이 Stage2 강제라 SMA150/200 지연 동안 초기돌파 차단, (2) buy가 supertrend flip 전용,
(3) 돌파일 setup_state가 과매수(cRSI −10)로 0이라 setup≥10 게이트가 돌파 buy를 막음.

**확정안 H′** (39종목 universe + PANW 검증):
- regime 상위티어 `trend_eligible = is_uptrend OR Stage2` (weak/above50/trend). NVDA는 Stage2 경로 유지.
- **fresh close-confirmed breakout**: `Close>prior20d高 AND 전일 아님`. 현 _detect_breakout(장중 고가)은
  5/4 wick(거래량0.66x)를 오분류 → 종가 확인으로 5/4 watch, 5/7 buy(거래량1.53x).
- buy = trend_eligible & ST up & !overextended & [ (fresh_flip & setup≥10) OR
  (fresh_breakout & near52 & setup≥0) ]. near52=종가 52주고점 -25% 이내(하락중 20일신고가 반등 배제).
- setup≥0(돌파 branch): 추세·ST·near52·종가돌파가 구조품질 담당, cRSI과매수로 10 올리면 재미검출.
- 거래량은 hard gate 아닌 confidence/evidence(추후 1.0/1.3/1.5x episode 성과 비교).
- 5/8+ 과열→hold(추격 억제), buy는 episode 최초 1회.

**검증**: H forward +3.1%/승률56%(baseline +2.7%/52%), 하락주티커 buy도 near52로 fwd +4.3%(무작위1.5%↑).
PANW 5/7 buy·5/8 hold. **잔여 리스크(정직)**: baseline 초과폭 +0.4%p로 얇음 → candidate-day가 아닌
**trigger episode 단위**로 median·MFE/MAE·하위10%·cluster bootstrap 재검증 필요(후속). buy는 hint.

### H′ 구현·검증 결과 (2026-09-15)
shadow_v2에 구현: regime trend 티어(is_uptrend|Stage2), fresh close-confirmed breakout, near52,
buy=[flip&setup≥10 | fresh_breakout&near52&setup≥0]. 신규 테스트(matrix breakout-buy 3 + PANW 회귀).
- **PANW**: 5/7 buy(entry O)·5/8 hold(과열) 회귀 고정. 사용자 사례 해결.
- 하락주 buy: naive H 165 → **H′ 56건**(near52 + 종가확인 돌파로 dead-cat 대폭 감소). LULU 3·NKE 5 등
  회복 시도 구간, 하락 구간(LULU 3/13~5/15)엔 buy 0(회귀 통과).
- BE/NVDA 안전성 유지, 전체 1380 통과.
- ⚠️ **정직**: H′ buy 집계 forward 20일 +2.6%/승률 49% ≈ baseline(2.7%/52%). 돌파 진입은 단기
  평균회귀라 20일 우위 얇음. buy는 **hint**(playbook이 authority). 진짜 판정엔 episode-level
  MFE/MAE·10일·bootstrap 재검증 필요(후속). recall(PANW류 미검출 방지)은 확보.

---

## Round 7 합의 (buy 타당성·성과) + flip-only buy 제거

사용자: 샘플 buy 시점·성과로 타당성 판단(리스크 일부 수용). episode 단위 + MFE/MAE 재검증.

**buy 에피소드 성과(297→flip제거 261, 39종목+PANW)**:
- forward 20일 평균 +2.3% / 중앙 −0.1% / 승률 49% (baseline +2.7%/52%) → **standalone 알파 아님**.
- 승자 +12.4% / 패자 −7.4%, MFE +10.4% / MAE −7.3% (비대칭). 큰 승자: INTC +98·CRWD +64·삼성 +51·
  BE +45·PANW 5/7 +38. 꼬리: LULU 하락중 돌파 −26·PLTR 고점 −16.
- codex 반박(수용): MFE는 사후 고점이라 청산수익 아님. 기대값 0.49×12.4−0.51×7.4≈+2.1%로 baseline 미달.
  비대칭이 baseline 열세를 독립적으로 상쇄하진 않음.

**합의**:
- buy는 **진입 후보 hint**로 타당(큰 상승 recall). standalone 20일 보유 전략으론 기각. playbook 승인+명시적
  stop 필수. LULU/PLTR형 꼬리는 그 관리로 흡수.
- **flip-only buy 제거**(채택): flip buy 약함(+0.7%)·최악 꼬리(ARM 고점 flip −29%) → buy는 종가 돌파로
  단일화. flip은 timing metadata/confidence로만 유지("ST 방향=상태, flip=trigger" 철학 유지).
- near52 25%→15%는 보류(과적합; LULU 1건 근거). 10/15/20/25% sweep(n·중앙·MFE/MAE·우측꼬리 recall) 후 재조정.

**구현**: decide_action_v2 buy = trend & ST up & !overext & fresh_close_breakout & near52 & setup≥0.
flip 제거 후 ARM −29% 꼬리 사라짐, PANW 5/7 유지. 전체 통과.
