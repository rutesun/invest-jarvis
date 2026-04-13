# Telegram 수집 파이프라인 설계서

**작성일**: 2026-04-11  
**상위 문서**: [invest-jarvis 비전 설계서](2026-04-11-invest-jarvis-vision.md)  
**커맨드**: `jarvis telegram fetch [DATE]` / `jarvis telegram catch-up`  
**하위 문서**: [Daily Report 설계서](2026-04-11-daily-report-design.md) (이 파이프라인을 데이터 소스로 사용)

---

## 목표

Telegram 채널 메시지를 날짜별 CSV로 수집·저장하는 파이프라인.  
Daily Report의 핵심 데이터 소스이며, 다른 파이프라인(Portfolio 등)에서도 종목 언급 grep으로 활용한다.

---

## 커맨드

```bash
jarvis telegram fetch [DATE]      # 특정 날짜 메시지 일괄 수집 (기본값: 전날)
jarvis telegram catch-up          # 마지막 수집 이후 누락분 보충
```

> 실시간 모니터링(sync)은 불필요. CRON 또는 수동 실행으로 운영.

---

## 아키텍처

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

---

## config.yaml 형식

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

---

## CSV 저장 형식

**파일 경로**: `data/YYYY-MM/YYYY-MM-DD-{channel_name}.csv`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| message_id | int | 메시지 고유 ID (중복 방지 키) |
| timestamp | str | ISO 형식, UTC |
| channel_name | str | 채널명 |
| author | str | 작성자 |
| content | str | 메시지 본문 |
| media_info | JSON | `{"type": "photo", "local_path": "data/media/..."}` |
| forward_from | str | 포워드 출처 |

---

## 미디어 다운로드

메시지에 첨부된 사진·PDF를 로컬에 저장하고, `media_info` 컬럼에 경로를 기록한다.

### 저장 경로

기존 `telegram` 프로젝트의 디렉토리 구조를 계승:

```
data/
├── images/YYYY-MM-DD/               # 사진
│   └── {channel}_{message_id}.jpg
├── files/YYYY-MM-DD/                # PDF 문서
│   ├── {channel}_{message_id}_{filename}.pdf      # 첨부 PDF
│   └── {channel}_url_{message_id}_{filename}.pdf  # URL PDF
└── YYYY-MM/
    └── YYYY-MM-DD-{channel}.csv     # 메시지 CSV
```

### 대상 미디어

| 타입 | Telethon 클래스 | 저장 위치 |
|------|----------------|----------|
| 사진 | `MessageMediaPhoto` | `data/images/YYYY-MM-DD/` |
| PDF 문서 | `MessageMediaDocument` (mime=`application/pdf`) | `data/files/YYYY-MM-DD/` |

- 사진: Telethon `client.download_media(message, file_path)`로 다운로드
- PDF: 문서 타입 중 `mime_type == "application/pdf"`인 것만 다운로드. 원본 파일명 보존.
- 그 외 미디어(동영상, 음성 등)는 **다운로드하지 않고** type/mime만 기록

### media_info 형식

사진:
```json
{"type": "photo", "local_path": "data/images/2026-04-13/channel_123.jpg"}
```

첨부 PDF:
```json
{"type": "document", "mime_type": "application/pdf", "local_path": "data/files/2026-04-13/channel_456_report.pdf"}
```

URL PDF (media_info 내 url_pdfs 배열):
```json
{"type": "document", "mime_type": "application/pdf", "local_path": "...", "url_pdfs": ["data/files/2026-04-13/channel_url_456_doc.pdf"]}
```

다운로드 대상이 아닌 미디어:
```json
{"type": "MessageMediaDocument", "mime_type": "video/mp4"}
```
> `local_path` 없이 type/mime만 기록.

### URL 내 PDF 다운로드

메시지 본문에 `.pdf` URL이 포함된 경우:
- httpx로 HEAD 요청 → `Content-Type: application/pdf` 확인 후 다운로드
- `data/files/YYYY-MM-DD/{channel}_url_{msg_id}_{filename}.pdf`에 저장
- `media_info`의 `url_pdfs` 배열에 경로 추가
- 다운로드 실패 시 경고 로그, 해당 URL 스킵

---

## 상태 관리

`data/monitor_state.json`으로 채널별 마지막 수집 메시지 ID 추적:
```json
{
  "123456789": 1000,
  "987654321": 5000
}
```
- 단조 증가 (monotonic): 더 큰 ID만 업데이트
- catch-up 시 Telegram read state와 비교하여 더 보수적인(이전) 지점부터 수집

---

## 중복 방지

CSV 저장 전 기존 파일에서 message_id 풀스캔 → 중복 시 스킵.

---

## 신규 모듈

| 모듈 | 역할 |
|------|------|
| `src/providers/telegram_client.py` | Telethon 클라이언트 설정 (API_ID, API_HASH) |
| `src/providers/telegram_collector.py` | 메시지 수집 (fetch/catch-up) |
| `src/providers/telegram_storage.py` | CSV 저장, 중복 방지, 미디어 다운로드 |
| `src/providers/telegram_state.py` | 상태 추적 (monitor_state.json) |
| `src/providers/telegram_loader.py` | CSV 로더 (Daily Report 및 다른 파이프라인에서 사용) |

---

## 환경 변수

```env
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
TELETHON_SESSION_NAME=anon   # 선택, 기본값 'anon'
```

---

## 기술 요구사항

| 항목 | 내용 |
|------|------|
| 신규 의존성 | `telethon` (Telegram API 클라이언트) |
| 환경 변수 | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` |
| 날짜 기준 | KST (파일명/디렉토리), 메시지 저장은 UTC ISO |
