# Change Record: Stock Report V2 Phase 2 — PDF ingest + semantic search

**Status**: Merged
**Date**: 2026-06-17
**PRs**: #41 (feature/stock-report-v2-phase2-pdf-ingest)
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

증권사 PDF 리포트가 DB 밖에 있어 synthesis LLM이 접근하지 못했다. 당일 텔레그램 메시지만으로는
분석가의 실제 수치·목표가·전망이 빠지고, "텔레그램 요약의 요약" 수준에 머문다. 969개 PDF 실측에서
97.5%가 born-digital(OCR 불필요)으로 확인되어, local 파싱 우선 + 필요 시 hybrid(docling) 라우팅
전략으로 결정했다.

## What

1. **PDF 파싱 경로 (`pdf_parser.py`)**: opendataloader-pdf를 local 모드로 래핑.
   0-byte·비PDF 사전 검증 포함. 배치 중 한 파일 실패가 전체를 죽이지 않도록 per-file fallback.
   Java 런타임 부재 시 명시적 오류.

2. **메타데이터 + 라우팅 (`pdf_metadata.py`)**: broker는 `config/stock_report_pdf_sources.yaml`
   최장 prefix 매칭, published_date는 폴더명, ticker는 본문 헤딩에서 추출(한국 6자리 +
   해외 `TICKER.EX` 패턴, 중국 `300308.CH` 포함). `needs_hybrid` 플래그는 "한 셀에 재무
   레이블 2개 이상" 규칙으로 fused-table 문서만 hybrid 라우팅. 38개 spike PDF 검증에서
   9개 flagged; 거시전략/시황은 local-only.

3. **청킹 품질 3라운드 (CP1~CP3, `pdf_chunking.py`)**:
   - CP1: text_char_count를 이미지/링크 마크업 제외 실본문 기준으로 수정. 래스터 PDF가
     body 363KB → 실 64자로 정정되어 `needs_ocr` 정상 감지.
   - CP2: heading 계층 기반 `section_path` + small-to-big 청킹(MAX 1500/MIN 200/OVERLAP 150).
     테이블은 ATOMIC 유지(절대 prose와 병합 안 함). 차트 pipe-block·`<br>` 잔여·출처줄 noise 제거.
   - CP3: 420→334청크(86 병합). 짧은 단편이 다음 청크에 prepend되어 타이틀 키워드 보존.
     `content_hash` 기반 문서 중복 차단(배치 내 + DB). 의미 단어 0개 청크 제거.

4. **LLM 카테고리 분류 (`pdf_classify.py`)**: 텔레그램과 동일 taxonomy로 분류해 T16 검색의
   `category_filter`와 좌표계를 맞춘다. 12개 문서 재적재 검증에서 LLM 분류가 규칙 fallback
   대비 정확(한국콜마 금융→소비재, 소부장 금융→반도체). LLM 실패·taxonomy 밖 값은 alias 규칙
   → 그래도 실패 시 `unclassified`(배치 안전).

5. **임베딩 분리 (`embed.py`)**: `STOCK_REPORT_EMBED_API_KEY` → `OPEN_AI_EMBEDDING_KEY` →
   `OPENAI_API_KEY` 우선순위 chain. `OPENAI_BASE_URL`(사내 gateway)은 임베딩 경로에서
   의도적으로 무시한다(gateway가 embeddings endpoint를 막는 경우 대응). 8000토큰 tiktoken 가드.

6. **2-pass 적재 오케스트레이션 (`pdf_ingest.py`)**: pass1 = parse→meta→upsert→chunk (DB 트랜잭션),
   pass2 = embed pending (트랜잭션 밖). OpenAI 호출을 DB 트랜잭션 안에 두지 않는 원칙.
   `content_hash + parser_version` 조합으로 멱등성 보장, `--reembed` 플래그로 강제 재처리.
   문서 단위 rollback이어서 한 PDF 실패가 배치를 중단시키지 않음.

7. **DB 스키마 (`migrations/008, 009`)**: `documents`(source_path UNIQUE, broker/ticker/date,
   parse_status, needs_hybrid, content_hash, markdown) + `document_chunks`(section_path/
   chunk_seq small-to-big, is_table, embedding vector(1536), HNSW 인덱스, embed_status async).
   `report_evidence`에 nullable `document_chunk_id` additive 추가 → Phase 1 회귀 없음.

8. **의미검색 (`retrieval.py`, T16)**: `search_document_chunks`에 `ticker_tags @> [ticker]`
   GIN exact 필터 + per-document ROW_NUMBER dedup 추가. `search_documents(query_text, *,
   category, ticker)` 래퍼가 embed → search → `DocumentSearchHit` 반환. T17 synthesis
   LLM이 function-calling 툴로 그대로 호출할 인터페이스.

## Before / After

```
Before:
  # PDF가 DB 밖에 있어 synthesis LLM 접근 불가
  # 리포트 근거 = 텔레그램 메시지 요약만

After:
  jarvis report ingest-pdf 2026-06-17
  → [OK] hana_005930_20260617.pdf → 334청크 → 임베딩 완료
  → [SKIP] shinhan_000660_20260617.pdf → content_hash 동일 (중복)
  → [HYBRID] kb_005935_20260617.pdf → fused-table 감지, hybrid 라우팅

  search_documents("반도체 목표주가 상향", category="반도체", ticker="005930")
  → [DocumentSearchHit] hana_005930 § 투자의견: 목표주가 95,000원(+15%)
  → [DocumentSearchHit] kb_005935 § HBM3E 수율 개선으로 실적 상향 조정
```

```
Before (임베딩 auth):
  OPENAI_BASE_URL 사내 gateway → embeddings endpoint 차단 → 오류

After:
  STOCK_REPORT_EMBED_API_KEY (우선) → OPEN_AI_EMBEDDING_KEY → OPENAI_API_KEY
  OPENAI_BASE_URL는 임베딩 경로에서 의도적으로 무시
```

## Impact

**신규 CLI**: `jarvis report ingest-pdf DATE [--input-dir/--use-hybrid/--ocr-lang/--embed-missing/--reembed]`

**DB 마이그레이션 선행 필요**: 008·009 마이그레이션 실행 후 ingest 가능.
`report_evidence` 테이블에 nullable 컬럼 하나 추가 → Phase 1 경로 회귀 없음.

**신규 환경변수**: `STOCK_REPORT_EMBED_API_KEY` (선택). 미설정 시 기존 `OPENAI_API_KEY` 사용.

**T17 의존성**: PDF가 실제 리포트 본문에 들어가는 것은 T17 완료 후. 이 단계에서는 ingest +
search capability만 제공하며 daily-v2 출력 변화는 없다.

## Constraints

- **T17 의존성**: PDF가 실제 리포트 본문에 들어가는 것은 T17에서 완성된다. 이 PR은
  ingest + search capability까지만 제공하며, synthesis 연결은 없다.
- **T11 보류**: Telegram chunk 임베딩 backfill은 의도적으로 미구현. PDF search와 좌표계를
  맞추는 설계 결정이 T17 시점에 맞춰지므로, 지금 backfill하면 나중에 재작업 가능성이 있다.
- **label truncation open question**: `needs_hybrid` 트리거가 fused-table은 잡지만
  label truncation(50022 패턴) 2번째 실패 유형은 감지 못 한다. 문서화만 하고 구현은 미뤘다.
- **DB 마이그레이션 선행 필요**: 008·009 마이그레이션 실행 전에는 ingest CLI가 동작하지 않는다.

## Related

- 설계: `docs/superpowers/specs/2026-06-04-stock-report-v2-pdf-ingest-design.md`,
  `docs/superpowers/specs/2026-06-15-t16-telegram-pdf-cross-link-design.md`
- 계획: `docs/superpowers/plans/2026-05-08-stock-report-engine-v2.md` (T12~T16 섹션),
  `docs/superpowers/plans/2026-06-15-t16-pdf-semantic-search.md`
- ADR: 없음
- FEATURES.md: PDF Ingest(5-2), T16 Semantic Search 섹션 추가 필요
- 후속: T17 (synthesis LLM function-calling 통합), T18 (PDF validation set)
