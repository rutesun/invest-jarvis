# Analyze Headline + KIS Fundamental Design

- Date: 2026-05-06
- Scope: `jarvis analyze`의 상단 판단 가독성 개선 + 한국 주식 펀더멘털 원천 교체
- Status: Draft for review

## 배경

실제 `제룡전기` 분석 출력에서 상단 `핵심 변수`가 짧은 판단 태그가 아니라 장문 본문으로 노출되었다.

예:

- `033100.KQ는 산업재 섹터의 특수 산업 기계 분야에 속해 있으며 ...`

이 문제는 상단 요약이 팩터 상세 설명과 같은 필드를 공유하기 때문에 발생한다.

동시에 한국 주식 펀더멘털은 현재 `yfinance` 기반이라 시가총액, 배당수익률, FCF 같은 값에서
현실감이 떨어지는 수치가 노출될 수 있다.

이번 보완의 목적은 다음 2가지다.

1. 상단 판단을 짧고 사람답게 만든다.
2. 한국 주식 펀더멘털 원천을 KIS 재무 API로 바꿔 숫자 신뢰도를 높인다.

## 목표

### 1. Headline / Detail 분리

상단 `핵심 변수`는 짧은 판단 라벨만 사용한다.

예:

- `고평가 부담`
- `기관 매수 우위`
- `단기 과열`

팩터 상세 섹션은 기존처럼 더 긴 문장 설명을 유지한다.

### 2. 한국 주식 펀더멘털 KIS 전환

한국 주식은 `yfinance` 대신 KIS 국내주식 재무 API를 사용한다.

사용 대상 API:

- `profit-ratio`
- `balance-sheet`
- `income-statement`
- `other-major-ratios`
- `financial-ratio`

미국/기타 종목은 기존 `yfinance` 경로를 유지한다.

## 비목표

- 미국 주식 펀더멘털 소스 변경
- KIS 기반 펀더멘털 LLM 프롬프트 대수술
- 밸류에이션 모델링 고도화
- CLI 전체 레이아웃 재설계

## 설계

### A. FactorAssessment 구조 변경

`src/pipelines/analyze_decision.py`

현재:

- `summary`: 상단 `핵심 변수`와 상세 팩터 문구에 모두 사용

변경:

- `headline: str | None`
- `summary: str`

의미:

- `headline`: 상단 `핵심 변수` 전용, 8~20자 내외의 짧은 라벨
- `summary`: 상세 팩터 설명용 문장

렌더링 규칙:

- 상단 `핵심 변수`는 `headline` 우선 사용
- `headline`이 없으면 `summary`를 짧게 축약한 fallback 사용
- 팩터 분류 섹션은 계속 `summary + 이유` 사용

### B. 팩터별 headline 규칙

#### 기술(가격)

예시 headline:

- `신고가 돌파`
- `단기 과열`
- `지지선 이탈`
- `추세 약화`

생성 방식:

- 현재 기술 요약의 첫 문장이 아니라, `total_score`, `bias`, 패턴/레벨 상태를 바탕으로 규칙 기반 생성

#### 수급

예시 headline:

- `기관 매수 우위`
- `외인·기관 동행`
- `수급 엇갈림`

생성 방식:

- 5일 방향성과 순매수 일수 기반 규칙 생성

#### 이벤트

예시 headline:

- `공급계약 재료`
- `규제 리스크`
- `신규 재료 제한적`

생성 방식:

- 뉴스/공시 키워드 및 방향성 기반 규칙 생성

#### 밸류에이션

예시 headline:

- `고평가 부담`
- `밸류 매력`
- `재무 신뢰도 낮음`

생성 방식:

- `valuation_assessment`
- `confidence`
- sanity check 결과
를 조합한 규칙 생성

### C. FundamentalTool 분기 구조

`src/tools/fundamental.py`

현재:

- 모든 종목이 `yfinance` 기반

변경:

- 한국 주식이면 KIS 기반 fetcher 사용
- 미국/기타 종목이면 기존 `yfinance` 사용

의사 코드:

```python
if is_korean_ticker(ticker):
    snapshot = await self._fetch_kis_fundamentals(ticker)
else:
    snapshot = await self._fetch_yfinance_fundamentals(ticker)
```

### D. KIS 데이터 조합 방식

한국 주식의 `FundamentalSnapshot`은 5개 KIS API 응답을 조합해 만든다.

#### 1. profit-ratio

우선 매핑 대상:

- `roe`
- `roa`
- `gross_margin`
- `operating_margin`
- `profit_margin`

#### 2. financial-ratio

우선 매핑 대상:

- `debt_to_equity`
- `current_ratio`
- `quick_ratio`

#### 3. other-major-ratios

우선 매핑 대상:

- `pe_ratio`
- `pb_ratio`
- `ps_ratio`
- `ev_ebitda`
- 필요 시 기타 보조 비율

#### 4. income-statement

우선 매핑 대상:

- 최근 분기 매출
- 최근 분기 순이익
- 분기/연간 성장률 계산 원천

#### 5. balance-sheet

우선 매핑 대상:

- 자산/부채/자본 보조값
- 필요 시 shares/자본 구조 보조값

### E. Snapshot 정규화 규칙

공통 출력 모델은 계속 `FundamentalSnapshot`을 유지한다.

원칙:

- KIS에 있는 값은 그대로 매핑
- 계산 가능한 값은 코드에서 계산
- KIS에 없거나 신뢰하기 어려운 값은 `None`
- CLI 출력에서는 `N/A`

즉 한국 주식에서 모든 필드를 억지로 채우지 않는다.

### F. 한국 주식 우선 원칙

한국 주식에서는 KIS 값을 source of truth로 본다.

`yfinance`를 혼합해 fallback하지 않는다.

이유:

- 데이터 단위 혼선 방지
- 소스 간 충돌 방지
- 판단 레이어의 일관성 유지

미국/기타 종목만 기존 `yfinance`를 유지한다.

### G. LLM 입력 정책

LLM 펀더멘털 요약은 계속 사용한다.

단:

- 상단 판단에는 LLM 장문을 올리지 않는다.
- 밸류에이션 팩터의 `headline`은 규칙 기반으로 만든다.
- 상세 `summary`는 LLM 문장을 유지할 수 있다.
- `None` 필드는 LLM 입력에서 제외하거나 `N/A`로 전달한다.

## CLI 출력 규칙

상단 판단:

- `주도 팩터`
- `핵심 변수`: `headline` 2~3개
- `액션`

하단 팩터 상세:

- `summary`
- `이유`
- `근거`

상세 펀더멘털:

- 없는 값은 숨기지 않고 `N/A`로 표시

## 테스트

### analyze_decision

- `headline`이 상단 `핵심 변수`에만 사용되는지
- `summary`는 상세 섹션에만 남는지
- 밸류에이션 장문 summary가 상단에 직접 노출되지 않는지

### fundamental

- 한국 주식이면 KIS fetcher 경로를 타는지
- 미국 주식이면 기존 `yfinance` 경로를 타는지
- KIS 누락 필드는 `None`으로 남는지
- 성장률 계산이 KIS 손익계산서 기준으로 동작하는지

### CLI

- 한국 주식에서 누락 펀더멘털이 `N/A`로 보이는지
- 상단 `핵심 변수`가 짧은 라벨로만 출력되는지

## 리스크

1. KIS 5개 API의 응답 필드명이 예상과 다를 수 있다.
2. 연간/분기 기준이 API마다 다를 수 있어 성장률 계산 로직 정합성 검증이 필요하다.
3. 기존 `FundamentalSnapshot` 필드와 KIS 실제 응답 사이에 1:1 대응이 안 되는 항목이 있을 수 있다.

## 구현 순서

1. KIS 재무 API 응답 스키마 확인 및 매핑표 작성
2. `FundamentalTool` 한국/해외 분기 추가
3. 한국 주식 KIS snapshot 정규화 구현
4. `FactorAssessment.headline` 추가
5. 상단 `핵심 변수` 렌더링을 headline 기반으로 교체
6. 테스트 추가 및 실제 한국 종목 재검증
