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
- 8개 컴포넌트 기반 분석
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
- **공시 분석** (최근 3개월 주요 공시, SEC/DART)
- **XBRL 재무데이터** (SEC/DART에서 재무지표 + YoY 비교 + 텍스트 인사이트)
- **수급 동향** (외인/기관 1d/5d/10d 순매수, 한국주식 전용)
- **종합 인사이트** (모든 팩터 통합 추천 + 리스크)
- **실행 가능한 투자 시그널** (Phase 2 강화):
  - 패턴 분석: 차트 패턴 해석 (Cup & Handle, Double Bottom 등)
  - 목표가: 시나리오별 가격 목표 (돌파 시/조정 시)
  - 진입 구간: 구체적 매수/매도 타이밍
  - 주요 레벨: 지지선/저항선 요약

- **차트 시각화**: 기술적 차트 PNG 자동 생성 (`charts/` 디렉토리)
  - 캔들스틱 + MA 라인 (20/50/200일)
  - Supertrend 추세선
  - 거래량 + MACD + RSI 패널
  - 패턴 마커 및 지지/저항선 표시

**선택 환경변수:**
- `OPENDART_API_KEY`: 한국주식 공시 조회 (없으면 공시 섹션 생략)
- `KIS_APP_KEY` / `KIS_APP_SECRET`: 수급 동향 조회 (없으면 수급 섹션 생략)

---

### 3. report - 일일 시장 리포트

#### 3-1. report ticker - 티커 기반 리포트

**특징:**
- 매크로 지표 스냅샷
- 다중 종목 기술적 분석
- 시장 전반 요약

**요구사항:**
- `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` 필요

**사용법:**
```bash
uv run jarvis report ticker [OPTIONS]
```

**옵션:**
- `--tickers, -t`: 분석할 티커 목록 (쉼표로 구분, 기본값: AAPL,MSFT,NVDA)
- `--provider, -p`: LLM 제공자 선택 (openai|anthropic, 기본값: openai)

**예시:**
```bash
# 기본 티커 사용
uv run jarvis report ticker

# 커스텀 티커
uv run jarvis report ticker --tickers "AAPL,GOOGL,META,TSLA"

# Anthropic 사용
uv run jarvis report ticker --provider anthropic
```

---

#### 3-2. report daily - 텔레그램 기반 일일 리포트

**특징:**
- 텔레그램 채널 메시지 자동 수집 및 분석
- MapReduce 패턴 5단계 파이프라인 (Ingest → Map → Shuffle → Reduce → Wrapup)
- 테마별 클러스터링 및 투자 인사이트 추출
- Claude Haiku 4.5 사용으로 비용 최적화
- `reports/YYYY-MM/daily_YYYY-MM-DD.md` 자동 저장
- Notion Database 연동 지원 (선택)

**요구사항:**
- 텔레그램 데이터 필요: `uv run jarvis telegram fetch <날짜>` 먼저 실행
- `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` 필요
- Notion 업로드 시: `NOTION_TOKEN`, `NOTION_DATABASE_ID` 필요 ([설정 가이드](../README_NOTION.md))

**사용법:**
```bash
uv run jarvis report daily [날짜] [OPTIONS]
```

**옵션:**
- `날짜`: 분석할 날짜 (YYYY-MM-DD). 미지정 시 전날
- `--data-dir, -d`: 데이터 디렉토리 (기본값: data)
- `--notion`: Notion에 업로드

**예시:**
```bash
# 전날 리포트 (MD 파일만 저장)
uv run jarvis report daily

# 특정 날짜 리포트
uv run jarvis report daily 2026-04-17

# Notion에도 업로드
uv run jarvis report daily 2026-04-17 --notion
```

**워크플로우:**
```bash
# 1. 텔레그램 메시지 수집 (먼저 실행 필요)
uv run jarvis telegram fetch 2026-04-17

# 2. 일일 리포트 생성
uv run jarvis report daily 2026-04-17
```

**출력 파일:**
- `reports/2026-04/daily_2026-04-17.md`

**리포트 구조:**
- 매크로 데이터 (VIX, Fear & Greed, 시장 지수, 환율)
- 핵심 인사이트 3-5개 (테마 간 관계 + 매크로 연결)
- 카테고리별 테마 분석
  - 투자 인사이트 테마명 (20-40자, 방향성 명확)
  - 이모지 + 요약 + 영향 + 관련 종목
  - 검색 키워드 (종목명, 기술용어, 트렌드)

**예시:**
```markdown
## 매크로 데이터
VIX: 15.2 | Fear & Greed: 65 (Greed)
미국: S&P500 +1.2%, NASDAQ +1.5% | 한국: KOSPI +0.5%

## 핵심 인사이트
💡 AI 인프라 투자 확대가 HBM 수요 증가로 이어지며 국내 반도체 업사이클 기대
🌊 미국 금리 인하 기대감 속 성장주 중심 랠리, 한국은 실적 검증 단계
⚠️ 중국 경기 둔화 우려가 이차전지·조선 섹터 리스크로 작용

## 반도체
### 🚀 GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜
...
```

**스테이지별 테스트:**
```bash
# 전체 파이프라인 한번에
./scripts/test_daily_report_stages.sh 2026-04-17

# 개별 스테이지 실행
uv run python -m src.pipelines.daily_report.stages.ingest_stage 2026-04-17
uv run python -m src.pipelines.daily_report.stages.map_stage 2026-04-17
uv run python -m src.pipelines.daily_report.stages.shuffle_stage 2026-04-17
uv run python -m src.pipelines.daily_report.stages.reduce_stage 2026-04-17
uv run python -m src.pipelines.daily_report.stages.wrapup_stage 2026-04-17
```

**상세 테스트 가이드:** [scripts/README_TESTING.md](../scripts/README_TESTING.md)

---

#### 3-3. report upload - 기존 리포트 일괄 업로드

**특징:**
- `reports/` 디렉토리의 기존 MD 파일을 Notion에 업로드
- 날짜 범위 지정 가능
- 리포트 타입 필터링 (daily, screener, all)
- 진행 상황 표시 및 에러 핸들링

**요구사항:**
- `NOTION_TOKEN`, `NOTION_DATABASE_ID` 필요 ([설정 가이드](../README_NOTION.md))

**사용법:**
```bash
uv run jarvis report upload [시작날짜] [종료날짜] [OPTIONS]
```

**옵션:**
- `--type, -t`: 리포트 타입 (`all`, `daily`, `screener`, 기본값: all)

**예시:**
```bash
# 전체 리포트 업로드
uv run jarvis report upload

# 특정 날짜만
uv run jarvis report upload 2026-04-22

# 날짜 범위 지정
uv run jarvis report upload 2026-04-17 2026-04-22

# Daily 리포트만
uv run jarvis report upload --type daily

# Screener 리포트만 (특정 날짜)
uv run jarvis report upload 2026-04-18 --type screener
```

**출력 내용:**
```bash
3개 리포트를 Notion에 업로드합니다...

✓ daily_2026-04-22.md → https://notion.so/...
✓ screen-2026-04-18.md → https://notion.so/...
✗ daily_2026-04-21.md 실패: Duplicate entry

완료: 성공 2, 실패 1
```

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
- `--notion`: Notion에 업로드

**예시:**
```bash
# MD 파일만 저장 (기본)
uv run jarvis screen

# 시장별 스크리닝
uv run jarvis screen --market kr
uv run jarvis screen --market us

# Notion에도 업로드
uv run jarvis screen --notion
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
