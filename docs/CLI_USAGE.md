# CLI 사용 가이드

## 실행 방법

### 방법 1: uv run 사용 (권장)
```bash
uv run jarvis check AAPL
uv run jarvis analyze AAPL
uv run jarvis report
```

### 방법 2: Shell Alias (더 짧게)
`~/.zshrc` (또는 `~/.bashrc`)에 추가:
```bash
alias jarvis="uv run jarvis"
```

적용:
```bash
source ~/.zshrc
```

이후 짧게 사용:
```bash
jarvis check AAPL
jarvis analyze AAPL
jarvis report
```

---

## 명령어 상세

### 1. check - 빠른 기술적 분석

**특징:**
- LLM 불필요 (빠른 응답)
- 5개 전략 기반 분석
- 주요 기술 지표만 출력

**사용법:**
```bash
uv run jarvis check <TICKER>
```

**예시:**
```bash
uv run jarvis check AAPL
uv run jarvis check MSFT
uv run jarvis check NVDA
```

**출력 내용:**
- 현재 가격 및 변동률
- 종합 평가 (매수/매도/중립)
- 신뢰도 점수
- 주요 지표 (SMA, RSI, ADX)
- 시그널 및 경고

---

### 2. analyze - 심층 분석 (LLM)

**특징:**
- 기술적 분석 + LLM 해석
- 최근 뉴스 감성 분석
- 투자 추천 및 근거

**요구사항:**
- `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` 필요

**사용법:**
```bash
uv run jarvis analyze <TICKER> [OPTIONS]
```

**옵션:**
- `--provider, -p`: LLM 제공자 선택 (openai|anthropic, 기본값: openai)

**예시:**
```bash
# OpenAI 사용
uv run jarvis analyze AAPL

# Anthropic 사용
uv run jarvis analyze AAPL --provider anthropic
```

**출력 내용:**
- 가격 및 변동률
- 기술적 분석 요약
- 투자 추천 (매수/매도/중립)
- 추천 근거 및 핵심 인사이트
- 뉴스 감성 분석
- 영향 평가 및 주요 테마

---

### 3. report - 일일 시장 리포트

**특징:**
- 매크로 지표 스냅샷
- 다중 종목 기술적 분석
- 시장 전반 요약

**요구사항:**
- `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` 필요

**사용법:**
```bash
uv run jarvis report [OPTIONS]
```

**옵션:**
- `--tickers, -t`: 분석할 티커 목록 (쉼표로 구분, 기본값: AAPL,MSFT,NVDA)
- `--provider, -p`: LLM 제공자 선택 (openai|anthropic, 기본값: openai)

**예시:**
```bash
# 기본 티커 사용
uv run jarvis report

# 커스텀 티커
uv run jarvis report --tickers "AAPL,GOOGL,META,TSLA"

# Anthropic 사용
uv run jarvis report --provider anthropic
```

**출력 내용:**
- **매크로 스냅샷:**
  - VIX (변동성 지수)
  - Fear & Greed Index
  - WTI Oil 가격
  - US 10Y/2Y 금리
  - Yield Spread
  - DXY (달러 지수)
- **티커 분석:**
  - 각 종목 가격 및 변동률
  - 종합 평가 및 신뢰도
  - 시그널 및 경고

---

### 4. portfolio - 포트폴리오 모니터링

**특징:**
- 실시간 보유 종목 조회 (KIS API)
- 각 종목 기술적 분석
- 최근 뉴스 요약
- 수익률 추적

**요구사항:**
- `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO` 필요

**사용법:**
```bash
uv run jarvis portfolio
```

**출력 내용:**
- 총 자산
- 현금 잔고
- 주식 평가액
- **보유 종목별:**
  - 종목명 및 티커
  - 보유 수량
  - 현재 가격
  - 손익 금액 및 비율
  - 기술적 평가 및 인사이트

---

### 5. screen - 시장 스크리너

**특징:**
- Naver 테마 + KIS 순위 기반 유니버스 구성
- 누적/상승일/거래량 폭발 지표 스코어링
- 후보 종목 랭킹 및 리포트 저장

**사용법:**
```bash
uv run jarvis screen [OPTIONS]
```

**옵션:**
- `--market, -m`: `kr`, `us`, `all` (기본값: all)

**예시:**
```bash
uv run jarvis screen
uv run jarvis screen --market kr
uv run jarvis screen --market us
```

---

### 6. cache - 티커 캐시 관리

종목명→티커 심볼 변환 결과를 로컬에 캐시합니다 (6개월 TTL).

```bash
uv run jarvis cache list      # 캐시된 매핑 목록
uv run jarvis cache clear     # 캐시 초기화 (확인 프롬프트)
uv run jarvis cache clear --yes  # 확인 없이 초기화
```

---

### 7. telegram - 텔레그램 채널 수집

**특징:**
- Telethon 기반 채널 메시지 수집
- include/exclude 정규식 필터링
- **채널별 timezone 설정 지원** (KST, UTC 등)
- 날짜별 CSV 저장 (중복 방지)
- catch-up 모드로 누락분 자동 보충
- **사진/PDF 자동 다운로드** (첨부파일 + URL)

**요구사항:**
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` 필요
- `config.yaml`에 `telegram.channels` 설정 필요
- 첫 실행 시 Telegram 인증 (전화번호/코드) 필요

**사용법:**
```bash
# 전날 메시지 수집 (기본)
uv run jarvis telegram fetch

# 특정 날짜 수집 (채널 timezone 기준)
uv run jarvis telegram fetch 2026-04-12

# 누락분 보충 수집
uv run jarvis telegram catch-up

# 커스텀 설정 파일
uv run jarvis telegram fetch --config my_config.yaml
```

**데이터 저장:**
- CSV: `data/YYYY-MM/YYYY-MM-DD-{channel_id}.csv` (채널 timezone 기준)
- 사진: `data/images/YYYY-MM-DD/{channel_id}_{msg_id}.jpg`
- 첨부 PDF: `data/files/YYYY-MM-DD/{channel_id}_{msg_id}_{filename}.pdf`
- URL PDF: `data/files/YYYY-MM-DD/{channel_id}_url_{msg_id}_{filename}.pdf`
- 상태: `data/monitor_state.json`

**파일명 규칙:** `channel_id`는 `config.yaml`에 설정한 영문 ID (예: "shinhanresearch")를 사용합니다.

---

### 첫 실행 가이드

#### 1. Telegram API 자격증명 발급

1. https://my.telegram.org/apps 접속
2. 로그인 후 "Create application" 클릭
3. `api_id`와 `api_hash`를 `.env`에 추가:

```bash
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
```

#### 2. 첫 실행 (인증)

**최초 1회만 필요**합니다:

```bash
$ uv run jarvis telegram fetch

Please enter your phone (or bot token): +821012345678  # 국가코드 포함
Please enter the code you received: 12345              # Telegram 앱에서 수신한 코드
```

인증 완료 후 `anon.session` 파일이 생성되며, **다음부터는 자동 로그인**됩니다.

#### 3. 채널 설정

`config.yaml`의 `telegram.channels`에 수집할 채널 추가:

```yaml
telegram:
  channels:
    - "channel_username"      # 간단한 형식 (timezone: UTC)
    
    - id: "korean_channel"    # 한국 채널 (KST)
      timezone: "Asia/Seoul"
    
    - id: "filtered_channel"  # 필터 + timezone
      timezone: "Asia/Seoul"
      include:
        - "Breaking|Urgent"   # 정규식
      exclude:
        - "(?i)ad|광고"
  output_dir: "data"
```

**중요: Timezone 설정**

메시지 timestamp는 UTC로 제공되지만, 채널 운영자는 보통 현지 시간대를 사용합니다.  
`timezone` 설정으로 메시지를 올바른 날짜에 저장할 수 있습니다.

**예시:**
- UTC 2026-04-08 23:14 발송 메시지
- `timezone: "Asia/Seoul"` 설정 시 → KST 2026-04-09 08:14
- **2026-04-09** 폴더에 저장 ✅

**지원 timezone:** [IANA Timezone Database](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)  
(예: `Asia/Seoul`, `America/New_York`, `Europe/London`, `UTC`)

---

### 문제 해결

**Q: 전화번호 입력 후 "Phone number invalid" 에러**  
A: 국가코드를 포함하세요 (한국: `+82`, 미국: `+1`)

**Q: 세션 파일 위치 변경?**  
A: `.env`에 `TELETHON_SESSION_NAME=my_session` 추가

**Q: 채널 ID를 모르겠어요**  
A: Telegram 앱에서 채널 정보 → "ID" 확인, 또는 `@channel_username` 사용

**Q: 비공개 채널이 수집 안 됨**  
A: 해당 Telegram 계정이 채널 멤버여야 수집 가능합니다

---

## 환경 변수 설정

### LLM API 키 (.env)
```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1  # 선택

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_BASE_URL=https://api.anthropic.com  # 선택
```

### KIS API 키 (.env)
```bash
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_ACCOUNT_NO=...
```

---

## 문제 해결

### "ModuleNotFoundError" 에러
```bash
# 의존성 재설치
uv sync --all-extras
uv pip install -e .
```

### jarvis 명령어를 찾을 수 없음
```bash
# uv run 사용
uv run jarvis --help

# 또는 alias 추가 (위 방법 2 참조)
```

### API 키 에러
```bash
# .env 파일 확인
cat .env

# 환경 변수 확인
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY
```

### 가격 데이터가 이상함 (nan, 0 등)
- yfinance API 일시적 장애일 수 있음
- 잠시 후 재시도
- 티커 심볼이 올바른지 확인

---

## 팁

### 1. 빠른 체크부터 시작
```bash
# 먼저 check로 빠르게 확인
uv run jarvis check AAPL

# 관심 있으면 analyze로 심층 분석
uv run jarvis analyze AAPL
```

### 2. 여러 종목 동시 분석
```bash
# report로 한 번에 여러 종목 체크
uv run jarvis report --tickers "AAPL,MSFT,GOOGL,AMZN,META"
```

### 3. 정기적인 모니터링
```bash
# cron이나 스케줄러로 자동화
0 9 * * 1-5 cd /path/to/invest-jarvis && uv run jarvis report
```

### 4. 출력 저장
```bash
# 파일로 저장
uv run jarvis check AAPL > aapl_analysis.txt

# 날짜별로 저장
uv run jarvis report > report_$(date +%Y%m%d).txt
```
