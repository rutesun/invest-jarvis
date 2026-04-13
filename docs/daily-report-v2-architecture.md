# Daily Report V2 아키텍처 및 렌더링 파이프라인 가이드

본 문서는 `invest-jarvis`의 데일리 리포트 파이프라인(`DailyReportV2Pipeline`)의 동작 방식 및 데이터 추출/보존 설계 사상에 대해 설명합니다. 특히 LLM의 "망각"과 "과도한 요약"을 방지하고 구체적인 팩트(뉴스 원문, 텔레그램 속보 원문)를 보존하기 위해 적용된 포인터(Pointer) 기반 렌더링 메커니즘을 다룹니다.

## 1. 개요 및 배경

초기 파이프라인 설계는 수집된 모든 요약 정보를 마지막 `Synthesize Stage`에서 LLM에게 한꺼번에 던져주고 `DailyReport` 객체로(문자열 3분할) 출력하도록 위임하는 형식이었습니다. 
이로 인해 발생한 **과도한 압축 문제(디테일 및 원문 유실, 데이터 Hallucination)**를 해결하고자, 텔레그램(Telegram) 수준의 디테일을 유지할 수 있는 형태의 **"원문 참조 분리 아키텍처"**로 개편되었습니다.

## 2. 파이프라인 데이터 흐름 (Data Flow)

파이프라인은 크게 **수집(Ingest) -> 추출(Map) -> 병합(Shuffle) -> 보강(Catalyst) -> 요약(Synthesize) -> 출력(Render)** 의 6단계로 나뉩니다.

### ① Ingest (수집 및 사전 생성)
수집된 방대한 텔레그램 원문 데이터를 그대로 LLM 체인들에 전송하지 않습니다.
대신 `IngestResult`에 `{메시지 ID : 원문 텍스트}` 형태의 사전인 `ref_lookup` 딕셔너리를 생성하여 저장해둡니다.
이후의 모든 컨텍스트 이동에서는 원문 텍스트를 제외시킨 채 가벼운 객체 이동만 일어납니다.

### ② Map (개별 이슈 추출)
LLM이 청크 단위로 분할된 메시지 집합에서 관련 이슈(`IssueExtract`)를 추출합니다. 
이 단계에서 해당 이슈가 어떤 메시지를 기반으로 나왔는지 `source_ids: list[int]` 필드에 **메시지 ID만 저장**하여 반환합니다. 

### ③ Shuffle (테마 기반 병합)
다양한 이슈들을 묶어 공통된 `Theme` (테마) 객체를 생성합니다.
이 과정에서 각 이슈 객체가 들고 있던 `source_ids`가 새로운 `Theme.source_ids`에 안전하게 병합되어 인계됩니다. (텍스트는 여전히 흐르지 않습니다.)

### ④ Catalyst (주도주 및 수급/뉴스 보강)
한국/미국 모멘텀 수급 데이터, 웹 검색을 통한 최신 뉴스 데이터가 종목 단위 객체(`StockCatalyst`)들에 보강됩니다.

### ⑤ Synthesize (시장 온도 총평)
마지막 LLM 호출 단계입니다. 여기서 LLM은 수집된 지표를 바탕으로 **시장 온도(Market Pulse)**와 **핵심 인사이트(Featured Analysis)**단 2개의 필드만 전문적으로 작성합니다. 세밀한 팩트 나열은 LLM의 임무가 아닙니다.

### ⑥ Render (마크다운 포매팅 조립)
`cli/main.py`의 렌더링 로직에서 데이터 조립이 일어납니다. 파이썬의 `for` 루프가 `Theme` 리스트와 `StockCatalyst` 리스트를 나열하며 수급 점수, 거래량, 테마 매핑을 출력합니다.
무엇보다 가장 핵심적으로, `Theme` 내부에 저장되어 있던 **`source_ids`의 숫자 값을 인덱스 삼아 맨 처음 만들어둔 `ref_lookup` 사전을 뒤져 텔레그램 속보 원문을 그대로 마크다운 [근거/원문]으로 삽입**합니다.

## 3. 핵심 데이터 구조 (`daily_report_models.py`)

주요 통신 객체 구조는 다음과 같습니다:

```python
# 1. 텔레그램 메시지 원문을 보관하는 사전이 포함된 수집본
class IngestResult(BaseModel):
    telegram_messages: list[dict]
    ref_lookup: dict[int, str]  # { ID: 텍스트 원본 }
    ...

# 2. 중간 이슈에서 단일 ID들을 보유
class IssueExtract(BaseModel):
    ...
    source_ids: list[int]

# 3. 테마로 병합된 후 누적된 ID 모음 보존
class Theme(BaseModel):
    ...
    source_ids: list[int] = Field(default_factory=list)

# 4. LLM이 최종 생성하는 정보는 이것으로 축소됨 (디테일 간섭 방지)
class DailyReportInsights(BaseModel):
    market_pulse: str
    featured_analysis: str

# 5. 파이프라인의 최종 출력물 (LLM 인사이트 + 보존된 원본 배열 + 사전)
class DailyReport(BaseModel):
    market_pulse: str              # LLM 생성
    featured_analysis: str         # LLM 생성
    themes: list[Theme]            # Python 추출/병합분
    catalysts: list[StockCatalyst] # Python 및 도구 보강본
    stock_details: dict            # 외부 API 연동 수치
    ref_lookup: dict[int, str]     # 렌더링용 뷰 모델 (Evidence 참조 테이블)
```

## 4. 장점 (Benefits)

1. **환각(Hallucination) 방지**: LLM에게 정보를 압축하고 긴 배열을 재출력하라고 지시할 필요가 사라졌기 때문에 사실 누락과 임의 창작이 방지됩니다.
2. **토큰 리미트 극복 및 토큰 절약**: 가장 무거운 텍스트 뭉치인 텔레그램 원문이 수집(Ingest) 단계에서만 로딩되고 LLM 프롬프트 속에서 지속적으로 오고가지 않기 때문에 토큰 리소스가 대폭 절감됩니다.
3. **가독성 증가**: 템플릿 마크다운 렌더링을 파이썬 코드가 직접 수행하므로 아이콘, 볼드체, 마크다운 문법의 커스터마이제이션(Customization)이 매우 자유롭고 일관적입니다.
