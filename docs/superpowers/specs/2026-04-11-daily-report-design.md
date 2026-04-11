# Daily Report 설계서

**작성일**: 2026-04-11  
**상위 문서**: [invest-jarvis 비전 설계서](2026-04-11-invest-jarvis-vision.md)  
**커맨드**: `jarvis daily-report`  
**실행 주기**: 수동

---

## 목표

매일 아침, 시장을 이해하기 위해 알아야 할 것들을 한 번에 정리한 리포트.
단순 뉴스 나열이 아니라, **"그래서 오늘 뭘 주목해야 하는가?"**에 답하는 것이 핵심.

---

## 선행 기능: Telegram 수집 파이프라인

Daily Report의 핵심 데이터 소스인 Telegram 수집이 아직 구현되지 않았다.
telegram 프로젝트의 수집 파이프라인을 이식하되, invest-jarvis 아키텍처에 맞게 재구성한다.

### 커맨드

```bash
jarvis telegram fetch [DATE]      # 특정 날짜 메시지 일괄 수집 (기본값: 전날)
jarvis telegram catch-up          # 마지막 수집 이후 누락분 보충
```

> 실시간 모니터링(sync)은 불필요. CRON 또는 수동 실행으로 운영.

### 아키텍처

```
config.yaml (채널 목록)
        ↓
  Telethon Client (API_ID, API_HASH)
        ↓
  ┌─────────────────────────────┐
  │  수집 모드 (2가지)            │
  │  ├─ fetch: 날짜 지정 일괄     │
  │  └─ catch-up: 누락분 보충     │
  └─────────────────────────────┘
        ↓
  메시지 처리 (process_message)
  ├─ include/exclude 필터링 (regex)
  ├─ 미디어 다운로드 (사진, PDF)
  └─ URL 내 PDF 다운로드
        ↓
  CSV 저장                      상태 추적
  data/YYYY-MM/                 monitor_state.json
  YYYY-MM-DD-{channel}.csv      {channel_id: max_msg_id}
```

### config.yaml 형식

telegram 프로젝트의 형식을 그대로 계승:

```yaml
channels:
  - "simple_channel_id"            # 전체 메시지 수집
  - id: "channel_with_filters"
    include:                         # 정규식 (OR 매칭)
      - "Breaking|Urgent"
    exclude:                         # 정규식 (ANY 매칭 시 제외)
      - "(?i)ad"

output_dir: "data"

link_processing:
  summarize_links_channels:
    - "kiwoom_semibat"
```

### CSV 저장 형식

**파일 경로**: `data/YYYY-MM/YYYY-MM-DD-{channel_name}.csv`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| message_id | int | 메시지 고유 ID (중복 방지 키) |
| timestamp | str | ISO 형식, UTC |
| channel_name | str | 채널명 |
| author | str | 작성자 |
| content | str | 메시지 본문 |
| media_info | JSON | `{"type": "photo", "local_path": "..."}` |
| forward_from | str | 포워드 출처 |

### 상태 관리

`monitor_state.json`으로 채널별 마지막 수집 메시지 ID 추적:
```json
{
  "123456789": 1000,
  "987654321": 5000
}
```
- 단조 증가 (monotonic): 더 큰 ID만 업데이트
- catch-up 시 Telegram read state와 비교하여 더 보수적인(이전) 지점부터 수집

### 중복 방지

CSV 저장 전 기존 파일에서 message_id 풀스캔 → 중복 시 스킵.

### 신규 모듈

| 모듈 | 역할 |
|------|------|
| `src/providers/telegram_client.py` | Telethon 클라이언트 설정 (API_ID, API_HASH) |
| `src/providers/telegram_collector.py` | 메시지 수집 (fetch/catch-up) |
| `src/providers/telegram_storage.py` | CSV 저장, 중복 방지, 미디어 다운로드 |
| `src/providers/telegram_state.py` | 상태 추적 (monitor_state.json) |
| `src/providers/telegram_loader.py` | CSV 로더 (Daily Report에서 사용) |

### 환경 변수

```env
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
TELETHON_SESSION_NAME=anon   # 선택, 기본값 'anon'
```

---

## Daily Report 파이프라인

### 1단계: 원시 데이터 수집 (병렬)

| 소스 | 수집 방법 | 비고 |
|------|-----------|------|
| Telegram 메시지 | 전날 CSV 전체 로드 | 채널 목록은 `config.yaml` |
| 시장 뉴스 | DDGS 검색 (한국/미국) | 키워드: 시장, 증시, 경제 등 |
| 매크로 지표 | yfinance (VIX, DXY, WTI, 금리) + Fear & Greed API | 기존 `macro.py` 활용 |
| Naver 테마 | 당일 상위 테마 + 구성 종목 | 기존 `naver.py` 활용 |
| 특징주 | 거래량/상승률 상위 + 외인/기관 수급 | Naver flow API |

### 2단계: LLM 분석 (Map-Reduce)

telegram 프로젝트의 V2 패턴을 계승하되 개선:

```
메시지 50개씩 청킹
        ↓
   [Map] 청크별 이슈 추출 (섹터, 카테고리, 토픽, 키워드)
        ↓
   [Filter] 키워드 정규화 + 빈도 상위 추출
        ↓
   [Reduce] 섹터별 이슈 통합 + 인사이트 생성
        ↓
   [Wrapup] 핵심 테마 5개 + 주요 이슈 7개 도출
```

**telegram 대비 개선 포인트:**
- Map 단계에서 **시장 영향 방향(Bull/Bear/Neutral)** 태깅 추가
- Reduce 단계에서 **테마 간 연결고리** 감지 (예: 금리 인상 → 은행 수혜 → 성장주 압박)
- Wrapup에서 **액션 레벨** 부여 (관심/모니터/즉시대응)

---

## 리포트 구성

### 섹션 1: 시장 전반

```markdown
## 오늘의 시장

### 매크로 스냅샷
| 지표 | 값 | 변동 | 시그널 |
|------|----|------|--------|
| VIX | 18.2 | -1.3 | 안정 |
| Fear & Greed | 62 | +5 | Greed |
| ...

### 주목 뉴스 Top 5
각 뉴스별:
- 요약 (2-3문장)
- 시장 영향: Bull/Bear/Neutral
- 연관 섹터
- **인사이트**: 왜 중요한가, 어떤 포지션에 영향을 미치는가
```

**인사이트 강화 제안:**
- **매크로 시그널 해석**: 단순 수치 나열이 아닌, 지표 조합의 의미를 해석. 예: "VIX 하락 + Fear&Greed 상승 = 리스크온 환경, 그러나 금리 역전 지속으로 경기침체 리스크는 여전"
- **전일 대비 변화량에 집중**: 절대값보다 변화의 방향과 속도가 더 중요

### 섹션 2: 테마별 시장 소식

**테마 목록 동적 생성:**
1. Naver 당일 상위 테마 자동 추출 (거래량/상승률 기준)
2. LLM이 Telegram/뉴스에서 Naver에 없는 신흥 테마 추가 감지

```markdown
## 테마별 브리핑

### 광통신
**모멘텀: 상승** | 관련 종목 수: 12

주요 소식:
- [뉴스/텔레그램] 요약...
- [뉴스/텔레그램] 요약...

주목 기업:
- AAAA: 이유 (수주 공시, 거래량 급증 등)
- BBBB: 이유

인사이트: 데이터센터 투자 확대에 따른 수혜 지속 전망.
다만 밸류에이션 부담 증가, 단기 차익실현 가능성.
```

**인사이트 강화 제안:**
- **테마 모멘텀 스코어**: 최근 5일 기준, 테마 내 종목들의 평균 상승률/거래량 변화로 모멘텀 방향 판단
- **테마 간 상관관계**: "AI 반도체 상승 → 데이터센터 수혜 가능" 같은 연쇄 효과 감지
- **Smart Money 시그널**: 테마 내 외인/기관 순매수 종목에 집중 — 개인 주도 vs 기관 주도 테마 구분

### 섹션 3: 특징주

```markdown
## 특징주

### 거래량 급등 + 기관/외인 매수
| 종목 | 가격 | 등락률 | 거래량배율 | 외인순매수 | 기관순매수 | 신호 |
|------|------|--------|-----------|-----------|-----------|------|
| AAAA | 50,000 | +8.5% | 3.2x | +50억 | +30억 | 매수 |

종목별 상세:
- **AAAA**: 5전략 빠른 체크 결과 + 관련 뉴스/텔레그램 1줄 요약
```

**인사이트 강화 제안:**
- **수급 필터링**: 단순 상승률 상위가 아닌, 외인+기관 동시 순매수 + 거래량 급등 조합 필터 (이른바 "Smart Money 특징주")
- **텔레그램 사전 언급 여부**: "어제 텔레그램에서 이미 언급됐던 종목" vs "오늘 처음 움직인 종목" 구분
- **스크리너 연계**: screener에서 이미 상위 랭크된 종목은 별도 표시 (기존 분석과 연결)

---

## 의미있는 인사이트를 위한 추가 제안

### 1. 시장 내러티브 생성
개별 뉴스/데이터의 나열을 넘어, LLM이 **하루의 시장 스토리**를 구성:
> "오늘 시장의 핵심은 OOO입니다. 미국 CPI 서프라이즈로 금리 인상 우려가 재점화되며
> 성장주 전반이 약세를 보였으나, AI 인프라 관련주는 NVDA 실적 호조에 힘입어
> 차별화된 강세를 이어갔습니다. 국내에서는 ..."

### 2. 과거 패턴 비교
비슷한 매크로 환경(VIX, 금리, Fear&Greed 조합)이었던 과거 시점과 비교:
- 그때 어떤 섹터가 움직였는가?
- 현재와 다른 점은?
→ 이 기능은 히스토리 데이터 축적 후 구현 가능 (장기 목표)

### 3. 포트폴리오 연계
Daily Report 마지막에 **내 포트폴리오에 대한 영향** 섹션:
- "오늘 뉴스 중 보유 종목 관련: AAAA(보유) — SEC 8-K 공시 발표, 확인 필요"
- Portfolio 점검 명령으로 연결

---

## 기술 요구사항

| 항목 | 내용 |
|------|------|
| 신규 의존성 | `telethon` (Telegram API 클라이언트) |
| 환경 변수 | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` |
| 기존 의존 모듈 | `macro.py`, `naver.py`, `news.py`, `technical/` |
| 신규 모듈 (수집) | `telegram_client.py`, `telegram_collector.py`, `telegram_storage.py`, `telegram_state.py` |
| 신규 모듈 (리포트) | `telegram_loader.py` (CSV 로더), `src/pipelines/daily_report_v2.py` |
| LLM 사용 | Map: gpt-4.1-mini, Reduce/Wrapup: claude-sonnet |
| 출력 | CLI 마크다운, Notion (선택) |

### 구현 순서

```
1. Telegram 수집 파이프라인 (수집 → CSV 저장 → 상태 관리)
   ↓
2. CSV 로더 + grep 검색 유틸리티
   ↓
3. Daily Report 파이프라인 (수집된 CSV + 뉴스 + 매크로 → Map-Reduce → 리포트)
```
