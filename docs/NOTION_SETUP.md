# Notion 연동 설정 가이드

## 1. Notion Integration 생성

1. https://www.notion.so/my-integrations 접속
2. **"+ New integration"** 클릭
3. 설정:
   - **Name**: invest-jarvis (또는 원하는 이름)
   - **Associated workspace**: 사용할 워크스페이스 선택
   - **Capabilities**: 
     - ✅ Read content
     - ✅ Update content
     - ✅ Insert content
4. **Submit** 클릭
5. **Integration Token** 복사 (형식: `secret_xxx...`)

---

## 2. Database 생성

1. Notion에서 새 페이지 생성
2. **Database** → **Table** 선택
3. **Database 이름**: "Daily Market Reports" (또는 원하는 이름)
4. **Properties** 추가:

| Property Name | Type | Description |
|---------------|------|-------------|
| Name | Title | 리포트 제목 (자동 생성) |
| Date | Date | 리포트 날짜 |
| VIX | Number | VIX 지수 |
| Fear & Greed | Number | Fear & Greed Index (0-100) |

5. Database 오른쪽 상단 **⋯** → **Connections** → **+ Add connections**
6. 1단계에서 생성한 Integration 선택

---

## 3. Database ID 확인

Database 페이지의 URL에서 ID 추출:

```
https://www.notion.so/{workspace}/{database_id}?v={view_id}
                                  ↑ 이 부분을 복사
```

**예시:**
```
https://www.notion.so/myworkspace/a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6?v=xxx
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

Database ID: `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6` (하이픈 없이)

---

## 4. 환경 변수 설정

`.env` 파일에 추가:

```bash
# Notion (일일 리포트 업로드)
NOTION_TOKEN=secret_xxx...  # Integration Token
NOTION_DATABASE_ID=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6  # Database ID
```

---

## 5. 사용법

### Daily Report 생성 + Notion 업로드

```bash
uv run jarvis report daily 2026-04-17 --notion
```

**출력:**
```
Daily Report 생성 중... (날짜: 2026-04-17)

[1/5] Ingest Stage...
...
✓ 리포트 저장: reports/2026-04/daily_2026-04-17.md
✓ Notion 업데이트 완료
```

### Notion만 업로드 (기존 리포트)

```python
from src.integrations.notion import update_daily_report
from src.pipelines.daily_report.models import DailyReport
import json

# wrapup 파일에서 로드
with open('tests/pipelines/daily_report/fixtures/stage_outputs/wrapup_2026-04-17.json') as f:
    data = json.load(f)

report = DailyReport(**data)
page_url = update_daily_report(report, '2026-04-17')
print(f'✓ Notion 페이지 생성: {page_url}')
```

---

## 6. 문제 해결

### "NOTION_TOKEN이 설정되지 않았습니다"
- `.env` 파일에 `NOTION_TOKEN=secret_xxx` 추가 확인
- Token이 `secret_`으로 시작하는지 확인

### "NOTION_DATABASE_ID가 설정되지 않았습니다"
- `.env` 파일에 `NOTION_DATABASE_ID=xxx` 추가 확인
- Database ID에서 하이픈(-) 제거했는지 확인

### "Could not find database"
- Database에 Integration이 연결되었는지 확인
- Database → **⋯** → **Connections** → Integration 추가

### "Unauthorized"
- Integration Token이 올바른지 확인
- Token이 만료되지 않았는지 확인 (Settings에서 재생성 가능)

### "Invalid property"
- Database의 Property 이름이 코드와 일치하는지 확인
- 필수: `Name` (Title), `Date` (Date), `VIX` (Number), `Fear & Greed` (Number)

---

## 7. 고급 설정

### Property 커스터마이징

`src/integrations/notion.py`의 `properties` 딕셔너리 수정:

```python
properties = {
    "Name": {"title": [{"text": {"content": title}}]},
    "Date": {"date": {"start": date}},
    "VIX": {"number": report.macro.vix},
    "Fear & Greed": {"number": report.macro.fear_greed},
    # 추가 Property
    "S&P 500": {"number": report.macro.us_markets["S&P500"]},
    "KOSPI": {"number": report.macro.kr_markets["KOSPI"]},
}
```

### 테마 개수 조정

기본값: 상위 10개 테마만 업로드

```python
for news_item in report.news[:10]:  # ← 이 숫자 변경
```

---

## 참고 링크

- [Notion API 문서](https://developers.notion.com/)
- [notion-client Python 라이브러리](https://github.com/ramnes/notion-sdk-py)
- [Database Properties 가이드](https://developers.notion.com/reference/property-object)
