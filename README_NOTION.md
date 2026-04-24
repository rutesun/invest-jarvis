# Notion 연동 Quick Start

## 빠른 설정 (3분)

### 1. Integration Token 발급
```bash
1. https://www.notion.so/my-integrations 접속
2. "+ New integration" → Name: invest-jarvis → Submit
3. Token 복사 (secret_로 시작)
```

### 2. Database 생성 및 연결
```bash
1. Notion에서 새 페이지 → Database (Table) 생성
2. Properties 추가 (통합 Database 구조):
   
   공통:
   - Name (Title)
   - Type (Select: Daily, Screener)
   - Date (Date)
   - Top Themes (Multi-select)
   
   Daily Report 전용:
   - VIX (Number)
   - Fear & Greed (Number)
   - KRW/USD (Number)
   - Insights Count (Number)
   
   Screener Report 전용:
   - Top Theme (Text)
   - KR Leaders (Number)
   - US Leaders (Number)
   - Theme Count (Number)
   
3. Database 우측 상단 ⋯ → Connections → Integration 추가
4. URL에서 Database ID 복사
```

**View 설정 (권장):**
- **All Reports**: 전체 (기본)
- **Daily Reports**: Type = Daily 필터
- **Screener Reports**: Type = Screener 필터
- **This Week**: Date = 최근 7일 필터

### 3. 환경 변수 설정
```bash
# .env 파일에 추가
NOTION_TOKEN=secret_xxx...
NOTION_DATABASE_ID=a1b2c3d4...
```

### 4. 사용
```bash
# Daily Report 생성 + Notion 업로드
uv run jarvis report daily 2026-04-17 --notion

# Screener Report + Notion 업로드
uv run jarvis screen --notion

# 기존 리포트 일괄 업로드
uv run jarvis report upload
uv run jarvis report upload 2026-04-17 2026-04-22  # 날짜 범위
uv run jarvis report upload --type daily            # 타입 필터

# MD 파일만 저장 (기본)
uv run jarvis report daily 2026-04-17
uv run jarvis screen
```

---

**상세 가이드**: [docs/NOTION_SETUP.md](docs/NOTION_SETUP.md)
