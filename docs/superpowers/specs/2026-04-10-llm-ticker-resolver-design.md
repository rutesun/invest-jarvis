# LLM 티커 리졸버 설계 문서

**작성일:** 2026-04-10  
**상태:** 승인됨

## 개요

`TickerResolver`의 yfinance 검색 fallback과 static yml 매핑을 GPT-4o + DuckDuckGo Tool Calling Loop(`LLMTickerAgent`)로 교체한다. 이를 통해 수작업 매핑 파일 없이도 한글 회사명(예: "삼성전자" → `005930.KS`)과 외국어 입력(예: "로켓랩" → `RKLB`)을 정확하게 해결할 수 있다.

## Resolution 파이프라인

```
resolve(query)
  ├─ 1. Direct ticker 감지     → 즉시 반환 (AAPL, 005930.KS 등)
  ├─ 2. 유저 캐시 조회          → 반환 + usage 업데이트
  └─ 3. LLMTickerAgent         → 검색 → 캐시 저장 → 반환
```

`config/ticker_names.yaml` 파일은 삭제한다. 이에 의존하던 `_load_static_mapping`, `_contains_korean`, static mapping 조회, `_search_yfinance` 메서드도 모두 제거한다.

## 데이터 모델

### CandidateTicker (변경 없음)

검색 결과에서 나온 후보 티커 하나를 나타낸다. yfinance를 제거하더라도 LLMTickerAgent가 여러 후보를 반환할 수 있는 경우를 위해 구조는 유지한다.

```python
class CandidateTicker(BaseModel):
    symbol: str        # 거래소 티커 심볼 (예: 005930.KS)
    name: str          # 회사 전체명 (예: Samsung Electronics Co., Ltd.)
    exchange: str      # 거래소 코드 (예: KSC, NMS)
    score: float       # 신뢰 점수 (0.0 ~ 1.0)
    quote_type: str    # 증권 유형 (예: EQUITY)
```

### TickerResolution (resolution_method 필드 변경)

티커 해결 결과 전체를 담는 모델. `resolution_method`에 `"llm_agent"` 값이 추가된다.

```python
class TickerResolution(BaseModel):
    original_query: str       # 사용자가 입력한 원본 쿼리 (예: 삼성전자)
    resolved_ticker: str      # 최종 결정된 티커 (예: 005930.KS)
    display_name: str         # 표시용 회사명 (예: Samsung Electronics)
    confidence: Literal["high", "medium", "low"]
    candidates: list[CandidateTicker]
    resolution_method: Literal[
        "direct_ticker",           # 사용자가 직접 티커 입력
        "user_cache",              # 이전에 해결된 결과를 캐시에서 조회
        "llm_agent",               # (신규) GPT-4o + DuckDuckGo로 해결
        # 제거: "static_mapping", "yfinance_search_single", "yfinance_search_multiple"
    ]
    source: str
```

### CachedMapping (변경 없음)

유저 캐시 파일(`~/.cache/invest-jarvis/user_mappings.yaml`)에 저장되는 개별 매핑 항목.

```python
class CachedMapping(BaseModel):
    ticker: str          # 저장된 티커 심볼
    display_name: str    # 저장된 표시명
    created_at: datetime # 최초 저장 시각
    last_used: datetime  # 마지막 사용 시각
    use_count: int       # 누적 사용 횟수
```

## 신규 컴포넌트

### `src/providers/llm_ticker_agent.py`

```python
class LLMTickerAgent:
    def __init__(self, api_key: str, model: str = "gpt-4o")
    async def resolve(self, query: str) -> tuple[str, str]  # (ticker, display_name)
```

**DuckDuckGo Tool:**

```python
@tool
def duckduckgo_search(query: str) -> str:
    """DuckDuckGo에서 검색하여 상위 5개 결과를 텍스트로 반환"""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
    return format_results(results)
```

**Tool Calling Loop 흐름:**

```
resolve("삼성전자")
  → GPT-4o에 시스템 프롬프트 + query 전달
  → LLM이 duckduckgo_search("삼성전자 stock ticker KRX") 호출
  → 검색 결과 반환
  → LLM이 결과 분석 → 추가 검색 or 티커 확정
  → 최종: {"ticker": "005930.KS", "display_name": "Samsung Electronics Co., Ltd."}
```

- LangChain `create_react_agent` 사용
- 최대 **3회** tool 호출; 초과 시 `TickerNotFoundError` 발생
- 최종 응답은 JSON 형식: `{"ticker": "...", "display_name": "..."}`

**시스템 프롬프트 핵심 지침:**
- 정확한 거래소 티커 심볼 반환 (예: `005930.KS`, `035720.KQ`, `RKLB`)
- 한국 KOSPI 종목은 `.KS`, KOSDAQ 종목은 `.KQ` suffix 포함
- 미국 종목은 suffix 없이 심볼만 (예: `AAPL`, `RKLB`)
- 응답 포맷: JSON `{"ticker": "...", "display_name": "..."}`

## 수정 파일 목록

| 파일 | 변경 유형 | 내용 |
|---|---|---|
| `src/providers/llm_ticker_agent.py` | 신규 | LLMTickerAgent 구현 |
| `src/providers/ticker_resolver.py` | 수정 | yfinance/static mapping 제거, LLMTickerAgent 연결 |
| `src/providers/ticker_models.py` | 수정 | resolution_method에 `"llm_agent"` 추가, 불필요 값 제거 |
| `pyproject.toml` | 수정 | `duckduckgo-search>=6.0.0` 의존성 추가 |
| `config/ticker_names.yaml` | 삭제 | 더 이상 사용하지 않음 |

## 캐시 동작

- `UserMappingCache` (`~/.cache/invest-jarvis/user_mappings.yaml`) 구조는 변경 없음
- `LLMTickerAgent.resolve()` 성공 후 `TickerResolver`가 `user_cache.save(query, ticker, display_name)` 호출
- 이후 동일 쿼리는 Step 2(캐시 조회)에서 즉시 반환, LLM 호출 없음

## 에러 처리

| 상황 | 동작 |
|---|---|
| `OPENAI_API_KEY` 미설정 | `LLMTickerAgent.__init__`에서 `ValueError` 발생 |
| LLM이 유효하지 않은 JSON 반환 | 최대 반복 횟수 내 재시도, 초과 시 `TickerNotFoundError` |
| DuckDuckGo 결과 없음 | LLM이 다른 검색어로 재시도 (최대 반복 횟수 내) |
| 최대 반복 횟수(3회) 초과 | `TickerNotFoundError` 발생, CLI로 전파 |

## 의존성

- `langchain-openai` — 기존 `pyproject.toml`에 포함
- `langchain-core` — 기존 `pyproject.toml`에 포함
- `duckduckgo-search>=6.0.0` — 신규 추가 필요

## 범위 외

- Anthropic/Claude를 티커 해결 LLM으로 사용하는 것 (OpenAI 전용 유지)
- `UserMappingCache` 구조 변경
- `report` 커맨드에 티커 해결 추가 (이미 raw 티커 직접 사용)
