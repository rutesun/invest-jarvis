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
