# Invest-Jarvis

금융 투자 분석을 지원하는 CLI 도구 및 Claude Code 스킬 기반 에이전트

## 주요 기능

### 1. 빠른 기술적 분석 (Quick Check)
```bash
jarvis check AAPL          # 티커로 검색
jarvis check Apple         # 회사명으로 검색
jarvis check 구글          # 한글 회사명으로 검색
jarvis check 005930        # 한국 주식 (6자리 코드)
jarvis check 005930.KS     # 한국 주식 (거래소 명시)
```
- 티커 또는 회사명으로 검색 가능 (자동 변환)
- 한글 회사명 지원 (예: 애플, 구글, 테슬라, 삼성전자)
- 검색 결과 자동 캐싱 (재검색 시 빠른 응답)
- 실시간 가격 및 변동률
- 5개 전략 기반 기술적 분석 (Trend, Oscillator, Divergence, Disparity, Risk)
- 이동평균선, RSI, MACD, ADX 등 주요 지표
- LLM 없이 빠른 응답

### 2. LLM 기반 심층 분석 (Deep Dive)
```bash
jarvis analyze AAPL        # 티커로 검색
jarvis analyze Apple       # 회사명으로 검색
jarvis analyze 구글        # 한글 회사명으로 검색
```
- 티커 또는 회사명으로 검색 가능
- 기술적 분석 + LLM 해석
- 최근 뉴스 감성 분석
- 투자 추천 및 근거 제시
- OpenAI/Anthropic 지원

### 3. 일일 시장 리포트 (Daily Report V2)
```bash
jarvis report
jarvis report --provider anthropic
jarvis report --stage ingest    # Stage별 독립 실행
```
- 텔레그램 + 뉴스 + 매크로 + 수급 데이터 병렬 수집
- LLM Map-Reduce로 시장 테마/내러티브 추출
- 주도주 촉매 뉴스 자동 매칭
- Stage별 독립 실행으로 프롬프트 튜닝 가능

### 4. 포트폴리오 모니터링
```bash
jarvis portfolio
```
- 보유 종목 현황 (KIS API 연동)
- 각 종목별 기술적 분석
- 최근 뉴스 요약
- 수익률 추적

### 5. 티커 캐시 관리
```bash
jarvis cache list          # 캐시된 매핑 목록 보기
jarvis cache clear         # 캐시 전체 삭제
```
- 회사명 → 티커 매핑을 자동으로 캐싱
- 재검색 시 빠른 응답
- 캐시는 ~/.cache/invest-jarvis/user_mappings.yaml에 저장
- 200개 항목 제한, 6개월 후 자동 만료

### 6. 텔레그램 채널 수집
```bash
jarvis telegram fetch               # 전날 메시지 수집
jarvis telegram fetch 2026-04-12    # 특정 날짜 수집
jarvis telegram catch-up            # 누락분 보충 수집
```
- Telegram 채널 메시지 자동 수집
- include/exclude 정규식 필터링
- 날짜별 CSV 저장 (중복 방지)
- catch-up 모드로 누락분 자동 보충
- 사진/PDF 자동 다운로드

### 7. Claude Code Skills
```
/invest-check AAPL
/invest-analyze AAPL
/invest-report
```
- Claude Code에서 대화형으로 사용 가능
- CLI 명령어를 가벼운 스킬로 래핑

---

## 설치

### 요구사항
- Python 3.12+
- uv

### 의존성 설치

```bash
# 개발 모드 설치 (권장)
uv sync --all-extras

# jarvis 명령어 설치 (선택)
uv tool install -e .
```

설치 후 두 가지 방법으로 실행 가능:
- `uv run jarvis` - uv를 통해 실행
- `jarvis` - PATH에 설치된 명령어 (uv tool install 후)

---

## 설정

### 1. 환경 변수 설정

`.env` 파일 생성:

```bash
cp .env.example .env
```

`.env` 파일 편집:

```bash
# LLM API Keys (analyze, report 명령어에 필요)
OPENAI_API_KEY=sk-...
# 또는
ANTHROPIC_API_KEY=sk-ant-...

# KIS API (한국 주식, portfolio 명령어에 필요)
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_ACCOUNT_NO=...

# Telegram API (telegram 명령어에 필요)
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
```

### 2. 전략 설정 (선택)

`config.yaml` 편집:

```yaml
technical:
  strategies:
    - trend
    - oscillator
    - divergence
    - disparity
    - risk

cache:
  quote_ttl: 60        # 1분
  history_ttl: 300     # 5분
  indicators_ttl: 300  # 5분
```

---

## 사용법

### CLI 명령어

```bash
# 버전 확인
uv run jarvis --version

# 도움말
uv run jarvis --help
uv run jarvis check --help

# 빠른 체크 (LLM 불필요)
uv run jarvis check AAPL           # 티커로 검색
uv run jarvis check Apple          # 회사명으로 검색
uv run jarvis check 구글           # 한글 회사명
uv run jarvis check 005930         # 삼성전자 (코드)
uv run jarvis check 삼성전자       # 삼성전자 (한글)

# 심층 분석 (LLM 필요)
uv run jarvis analyze AAPL
uv run jarvis analyze Apple        # 회사명도 가능
uv run jarvis analyze TSLA --provider anthropic

# 일일 리포트 (LLM 필요) - V2: 테마 중심
uv run jarvis report
uv run jarvis report --provider anthropic

# 포트폴리오 (KIS API 필요)
uv run jarvis portfolio

# 티커 캐시 관리
uv run jarvis cache list           # 캐시 목록
uv run jarvis cache clear          # 캐시 삭제
```

### Claude Code Skills

Claude Code에서 대화형으로 사용:

```
나: AAPL 주가 체크해줘
Claude: /invest-check AAPL

나: AAPL 심층 분석해줘
Claude: /invest-analyze AAPL

나: 오늘 시장 리포트 만들어줘
Claude: /invest-report
```

---

## 아키텍처

### 레이어 구조

```
┌─────────────────────────────────────┐
│     CLI / Claude Code Skills        │
├─────────────────────────────────────┤
│   Pipelines (Quick, Deep, Report)   │
├─────────────────────────────────────┤
│   Tools (Technical, News, Macro)    │
├─────────────────────────────────────┤
│   Providers (YFinance, KIS)         │
├─────────────────────────────────────┤
│   Storage (Cache)                   │
└─────────────────────────────────────┘
```

### 주요 컴포넌트

**Providers** - 데이터 소스 래퍼
- `YFinanceProvider`: 미국 주식 데이터
- `KISProvider`: 한국 주식 데이터 (KIS API)

**Tools** - 분석 도구
- `TechnicalAnalysisTool`: 5개 전략 기반 기술 분석
- `MacroTool`: 매크로 지표 (VIX, Fear & Greed, 금리 등)
- `NewsTool`: 뉴스 수집
- `PortfolioTool`: 포트폴리오 조회

**Strategies** - 기술적 분석 전략
- `TrendStrategy`: 이동평균선, ADX, Supertrend
- `OscillatorStrategy`: RSI, Stochastic, CCI
- `DivergenceStrategy`: 가격-지표 다이버전스
- `DisparityStrategy`: 이격도 분석
- `RiskStrategy`: 변동성 및 리스크 평가

**Pipelines** - 워크플로우
- `QuickCheckPipeline`: 빠른 기술 분석 (LLM 불필요)
- `DeepDivePipeline`: 기술 + 뉴스 + LLM 해석
- `DailyReportPipeline`: 매크로 + 다중 종목 분석
- `PortfolioPipeline`: 포트폴리오 모니터링

**LLM Client** - AI 분석
- OpenAI (GPT-4)
- Anthropic (Claude)
- 재현 가능한 파라미터 (temperature=0, seed=42)

---

## 개발

### 테스트 실행

```bash
# 전체 유닛 테스트
uv run pytest tests/ -v --ignore=tests/integration

# 특정 모듈 테스트
uv run pytest tests/tools/technical/ -v

# 통합 테스트 (API 키 필요)
export OPENAI_API_KEY=sk-...
uv run pytest tests/integration/ -v -m integration

# 커버리지 포함
uv run pytest tests/ --cov=src --cov-report=html
```

### 새 전략 추가

1. `src/tools/technical/strategies/` 에 새 전략 클래스 작성
2. `BaseStrategy` 상속 및 `analyze()` 메서드 구현
3. `src/tools/technical/registry.py`의 `STRATEGY_MAP`에 추가
4. `config.yaml`의 `strategies` 리스트에 추가
5. 테스트 작성 및 실행

예시:
```python
# src/tools/technical/strategies/my_strategy.py
from src.tools.technical.base import BaseStrategy
from src.tools.technical.models import StrategyResult

class MyStrategy(BaseStrategy):
    name = "my_strategy"
    description = "My custom strategy"
    
    def analyze(self, df: pd.DataFrame) -> StrategyResult:
        # 분석 로직
        return StrategyResult(...)
```

### 코드 스타일

- 타입 힌트 사용
- Pydantic 모델로 데이터 검증
- TDD 방식 (테스트 먼저 작성)
- 영어 코드, 한글 주석 가능

---

## 프로젝트 구조

```
invest-jarvis/
├── src/
│   ├── core/              # 핵심 인터페이스 및 설정
│   ├── providers/         # 데이터 제공자 (yfinance, KIS)
│   ├── tools/            # 분석 도구
│   │   └── technical/    # 기술적 분석 (전략, 지표)
│   ├── storage/          # 캐시
│   ├── llm/              # LLM 클라이언트
│   ├── pipelines/        # 파이프라인
│   └── cli/              # CLI 진입점
├── skills/               # Claude Code 스킬
├── tests/                # 테스트
├── config.yaml           # 설정 파일
├── pyproject.toml        # 프로젝트 메타데이터
└── .env.example          # 환경 변수 템플릿
```

---

## API 키 발급

### OpenAI API
1. https://platform.openai.com/api-keys 접속
2. "Create new secret key" 클릭
3. 키 복사 후 `.env`에 저장

### Anthropic API
1. https://console.anthropic.com/settings/keys 접속
2. "Create Key" 클릭
3. 키 복사 후 `.env`에 저장

### KIS API (한국투자증권)
1. KIS Developers (https://apiportal.koreainvestment.com) 가입
2. 앱 등록 후 APP Key/Secret 발급
3. `.env`에 저장

---

## 버전 히스토리

### v0.4.1 (2026-04-13)
- Daily Report V2 파이프라인 안정화
- KIS API race condition 수정 (asyncio.Lock 추가)
- Map stage 모델 변경 (gpt-4o-mini → gpt-4o, 게이트웨이 제한 해결)

### v0.4.0 (2026-04-09)
- 회사명으로 티커 검색 (영문/한글 지원)
- 티커 자동 변환 (Apple → AAPL, 구글 → GOOGL)
- 정적 매핑 (한글 회사명 → 영문)
- yfinance Search API 연동
- 사용자 캐시 시스템 (자동 저장, 6개월 만료)
- `jarvis cache` 명령어 (list/clear)

### v0.3.0 (2026-04-09)
- 한국 주식 지원 (KIS API)
- 포트폴리오 모니터링
- Claude Code Skills

### v0.2.0 (2026-04-09)
- LLM 기반 분석 (OpenAI/Anthropic)
- 4개 전략 추가 (총 5개)
- Macro/News 도구
- Deep Dive/Daily Report 파이프라인

### v0.1.0 (2026-04-08)
- Core 인터페이스 및 YFinance provider
- Technical 분석 (Trend 전략)
- Quick Check 파이프라인
- CLI `check` 명령어

---

## 라이선스

MIT

---

