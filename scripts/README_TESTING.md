# Daily Report Pipeline 테스트 가이드

## 빠른 시작

### 전체 Stage 한번에 테스트
```bash
./scripts/test_daily_report_stages.sh 2026-04-14
```

출력:
- 각 Stage 진행 상황 (Ingest → Map → Shuffle → Reduce → Wrapup)
- 메트릭 요약 (압축률, 평균 소스/이슈, 테마 수, 인사이트 수)
- 생성된 JSON 파일 목록

---

## Stage별 개별 테스트

### 1. Ingest Stage (CSV + 매크로 로드)
```bash
uv run python -m src.pipelines.daily_report.stages.ingest_stage 2026-04-14
```

**출력:**
- 로드된 메시지 개수
- VIX, Fear & Greed
- 미국/한국 시장 변동률
- 저장 경로: `tests/.../ingest_2026-04-14.json`

### 2. Map Stage (이슈 추출)
```bash
uv run python -m src.pipelines.daily_report.stages.map_stage 2026-04-14
```

**출력:**
- 추출된 이슈 개수
- 테마 통계 (총/고유)
- 평균 소스/이슈
- 저장 경로: `tests/.../map_2026-04-14.json`

### 3. Shuffle Stage (테마 정규화)
```bash
uv run python -m src.pipelines.daily_report.stages.shuffle_stage 2026-04-14
```

**출력:**
- 정규화된 테마 개수
- 재그룹핑된 이슈 개수
- 저장 경로: `tests/.../shuffle_2026-04-14.json`

### 4. Reduce Stage (테마별 분석)
```bash
uv run python -m src.pipelines.daily_report.stages.reduce_stage 2026-04-14
```

**출력:**
- 분석된 테마 개수
- 뉴스 검색 및 LLM 분석
- 저장 경로: `tests/.../reduce_2026-04-14.json`

### 5. Wrapup Stage (최종 리포트)
```bash
uv run python -m src.pipelines.daily_report.stages.wrapup_stage 2026-04-14
```

**출력:**
- 핵심 인사이트 개수
- 메타 인사이트 출력
- 저장 경로: `tests/.../wrapup_2026-04-14.json`

---

## 결과 확인

### JSON 출력 보기
```bash
# 상위 3개 이슈 확인
jq '.[0:3] | .[] | {title, themes, source_count: (.source_ids | length)}' \
  tests/pipelines/daily_report/fixtures/stage_outputs/map_2026-04-14.json

# 특정 이슈 상세
jq '.[0]' tests/pipelines/daily_report/fixtures/stage_outputs/map_2026-04-14.json
```

### 메트릭 계산
```bash
# 압축률
jq '. | length' tests/.../map_2026-04-14.json

# 평균 소스/이슈
jq '[.[] | .source_ids | length] | add / length' tests/.../map_2026-04-14.json

# 고유 테마 수
jq '[.[] | .themes[]] | unique | length' tests/.../map_2026-04-14.json
```

---

## LangSmith 추적

### 설정 확인
```bash
# 환경변수 확인
env | grep LANGSMITH

# 또는
cat .env | grep LANGSMITH
```

### 필수 환경변수 (.env)
```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=invest-jarvis
```

### LangSmith에서 확인
1. https://smith.langchain.com 접속
2. Projects → invest-jarvis
3. **Filters로 그룹핑:**
   - Tags: `map_stage`, `shuffle_stage`, `reduce_stage`, `wrapup_stage`
   - Tags: `date:2026-04-14` (날짜별 필터링)
   - Tags: `theme:테마명` (Reduce stage에서 테마별 필터링)

**Run Name 패턴:**
- Map: "Map Stage - 2026-04-14 - Chunk 1"
- Shuffle: "Shuffle Stage - 2026-04-14"
- Reduce: "Reduce Stage - 2026-04-14 - 테마명"
- Wrapup: "Wrapup Stage - 2026-04-14"

**추적되는 정보:**
- 프롬프트 입력/출력
- 토큰 사용량
- 실행 시간
- 에러 로그
- Metadata (stage, date, chunk_index, theme 등)

---

## pytest 테스트

### Unit 테스트만
```bash
uv run pytest tests/pipelines/daily_report/ -v -m "not integration"
```

### 통합 테스트 포함 (LLM 호출)
```bash
uv run pytest tests/pipelines/daily_report/ -v
```

### 특정 Stage만
```bash
uv run pytest tests/pipelines/daily_report/test_map_stage.py -v
```

---

## 프롬프트 튜닝 워크플로우

1. **현재 버전 실행**
```bash
./scripts/test_daily_report_stages.sh 2026-04-14
```

2. **결과 평가**
```bash
# 압축률 목표: 20-40%
# 평균 소스/이슈 목표: 3-5개
# 고유 테마 목표: 20-40개
```

3. **프롬프트 수정**
```python
# src/pipelines/daily_report/prompts.py
MAP_PROMPT_V4 = """..."""
MAP_PROMPT = MAP_PROMPT_V4
```

4. **재실행 및 비교**
```bash
./scripts/test_daily_report_stages.sh 2026-04-14

# 이전 결과와 비교
diff tests/.../map_2026-04-14.json.backup tests/.../map_2026-04-14.json
```

5. **개선 시 커밋**
```bash
git add src/pipelines/daily_report/prompts.py
git commit -m "prompt: Map 클러스터링 개선 (v3→v4)

변경사항: ...
결과:
- 압축률: X% → Y%
- 평균 소스/이슈: A → B
"
```

---

## 문제 해결

### "ModuleNotFoundError: No module named 'src'"
```bash
# 프로젝트 루트에서 실행 확인
pwd  # /Users/user/Develop/My/invest-jarvis

# 또는 PYTHONPATH 설정
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### LangSmith 추적 안 됨
```bash
# .env 파일 확인
cat .env | grep LANGSMITH

# dotenv 설치 확인
uv pip list | grep python-dotenv
```

### JSON 파싱 에러
```bash
# JSON이 올바른지 확인
jq '.' tests/.../map_2026-04-14.json | head -20

# LLM 응답 확인 (프롬프트 개선 필요)
```
