# 기술 부채 (Tech Debt)

> 동작에는 문제가 없지만 향후 개선이 필요한 구조적 항목을 기록한다.
> 당장의 버그가 아니라 "나중에 그 코드를 만질 때 함께 정리할" 대상이다.
> 버그는 `docs/FEATURES.md`의 버그 수정 섹션에, 설계는 `docs/superpowers/specs/`에 기록한다.

---

## 1. debate grounding 함수가 실제 흐름에 미연결 (2026-06-17, Low)

**현황**: `src/pipelines/debate/grounding.py`의 `points_grounding_ratio`(LLM 논거가 증거에 근거하는지 비율 계산 = 환각 탐지)는 테스트에서만 호출되고, `src/pipelines/debate/engine.py`의 debate 실행 흐름에는 연결되어 있지 않다.

**왜 부채인가**: 환각 검출 안전장치를 만들어 두고 켜지 않은 상태다. 나중에 debate를 강화할 때 이 함수의 존재를 모르고 같은 기능을 중복 구현할 위험이 있다.

**개선 방향**: debate 본격 강화 시점에 (1) 토큰 매칭 방식의 정밀도 개선(현재 한글/영문 혼재로 멀쩡한 논거를 환각으로 오판할 수 있음) 후 (2) `run_debate_judge` 결과에 연결해 ungrounded 논거를 거른다. 쓰지 않기로 하면 함수와 테스트를 함께 제거한다.

---

## 2. CLI 렌더가 분석 결과 내부 dict 구조를 직접 파싱 (2026-06-17, 구조)

**위치**: `src/cli/analyze_render.py`의 `format_deep_dive_output` — `technical.components["minervini"]["metrics"]["supertrend_value"]` 등 내부 dict를 키 문자열로 직접 조회한다.

**왜 부채인가**: 화면(CLI) 레이어가 분석(tools) 레이어의 내부 계산 구조에 결합돼 있다. `minervini`/`supertrend` 컴포넌트가 metrics 키 이름을 바꾸면 렌더가 조용히 `None`을 표시하고 테스트도 통과한다(에러 없음). 실제로 `sma_20_slope`/`sma_50_slope`는 minervini가 계산하지 않아 항상 None이 되는 계약 불일치가 이미 존재한다.

**개선 방향**: 분석 결과를 정형 모델(예: `TechnicalResult.snapshot` 또는 별도 `Stage2Display`)에 `supertrend_value: float | None`, `sma_slopes: dict[int, float]` 같은 명시 필드로 담아 `tools → pipelines → cli` 방향으로 전달하고, CLI는 그 필드만 읽는다. CLI가 components dict 구조를 알 필요가 없게 한다.

---

## 3. pipelines/debate 모델이 llm 레이어 타입을 직접 포함 (2026-06-17, 구조)

**위치**: `src/pipelines/debate/models.py` — `from src.llm.models import DebateCase, DebateVerdictOutput`. pipeline 출력 계약인 `DebateBundle`이 LLM I/O 타입을 내부에 박고 있다.

**왜 부채인가**: `DebateBundle`을 소비하는 CLI·테스트·다른 파이프라인이 모두 `llm.models`를 간접 의존하게 된다. LLM 응답 스키마를 바꾸면 pipeline 모델 계약까지 전파된다.

**개선 방향**: `DebateCase`/`DebateVerdictOutput`을 pipeline 도메인 모델로 분리하고 llm 레이어가 그것을 import하도록 방향을 역전하거나, LLM I/O 타입과 pipeline 출력 타입을 분리하는 중간 계층을 둔다. 단방향 흐름(`Providers → Tools → Pipelines → LLM → CLI`)에 맞춘다.

---

## 4. RS 강세 판정 시간축 불일치 + 소스 혼합 — IBD 통일 미적용 (2026-06-17, 설계 완료·구현 보류)

**설계 문서**: `docs/superpowers/specs/2026-06-17-ibd-rs-unification-design.md` (구현 플랜은 작성 예정)

**현황**: 종목 RS(`RelativeStrengthResult.is_strong` = Mansfield 52주 + 4주 기울기, 다기간)와 미국 업종 강세(`SectorStrengthResult.is_strong` = FMP 하루 등락률 순위 `rank_pct` + 60일 추세, 하루 rank가 게이트)가 **시간축이 다르다**. 또 한국 종목 RS는 분자(KIS 종가)와 분모(yfinance 코스피 `^KS11`) **데이터 소스가 혼합**돼 있다. 통일 설계는 완료됐으나 미구현.

**왜 부채인가**: 같은 "상대강도" 개념인데 종목은 1년, 업종은 하루를 본다. 하루 급락 한 번이 60일 추세가 좋은 업종을 즉시 `업종강세=False`로 떨어뜨린다(2026-06-16 "Electrical Equipment & Parts" 당일 -4.96%, 하위 2위로 BE가 업종강세=False가 된 실증). 한국 RS는 서로 다른 소스의 종가를 나눠 계산하는 일관성 결함이 있다. FMP `historical-industry-performance`는 21거래일치·2024-03에서 멈춘 데이터라 업종 IBD 계산 자체가 불가능하다.

**개선 방향**(spec 요지): 종목·업종·미국·한국을 모두 IBD 가중 강도 공식(분기 0.4/0.2/0.2/0.2 가중, 지수 대비 비율 100 기준)으로 통일하고 `is_strong = ibd_rs > 100`. 미국 업종은 대표 ETF(세부 ETF 우선 + SPDR 섹터 fallback) yfinance close, 한국은 전부 KIS(업종지수 페이징 추가). FMP·`rank_pct`·`trend` 제거. `RsSeriesProvider` 추상화로 시장 독립 판정. Mansfield·rs_cross는 보조·이벤트용으로 유지. 상세·매핑·테스트 전략은 spec 참조.
