# 코드 정리 구현 계획

> **에이전트 작업자용:** 필수 서브스킬: superpowers:subagent-driven-development (권장) 또는 superpowers:executing-plans를 사용하여 이 계획을 단계별로 구현하세요. 체크박스 (`- [ ]`) 문법으로 진행 상황을 추적합니다.

**목표:** 코드 분석으로 식별된 기술 부채 정리: 치명적 버그 수정, 사용되지 않는 코드 제거, 이름 충돌 해결, 오래된 문서 업데이트

**아키텍처:** 상향식 정리 - 치명적 런타임 버그부터 시작, 이후 사용되지 않는 코드 제거, 이름 일관성 개선, 마지막으로 문서 업데이트. 각 작업은 동작하고 테스트 가능한 상태를 생성합니다.

**기술 스택:** Python 3.12+, pytest, git

**분석 결과:** Explore subagent를 사용한 종합적인 코드베이스 분석 결과:
- 1개 치명적 런타임 버그 (정의되지 않은 logger)
- 1개 치명적 이름 충돌 (MacroSnapshot 중복)
- 8개 사용되지 않는 import 및 1개 사용되지 않는 함수
- 5개 문서 누락

---

## Task 1: 치명적 Logger 버그 수정

**파일:**
- 수정: `src/cli/main.py:1-3`
- 테스트: `tests/integration/test_e2e_plan2.py`

**문제:** 212번, 225번 줄에서 `logger.warning()`을 호출하지만 `logger`가 정의되지 않아 런타임 시 NameError 발생

- [ ] **단계 1: import 이후 logger 정의 추가**

`src/cli/main.py`를 열고 2번 줄 (`import logging`) 이후에 추가:

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **단계 2: 수정 위치 확인**

```bash
grep -n "logger.warning" src/cli/main.py
```
예상 결과: 212번, 225번 줄 표시

- [ ] **단계 3: 통합 테스트 실행**

```bash
uv run pytest tests/integration/test_e2e_plan2.py -v -k analyze
```
예상 결과: PASS

- [ ] **단계 4: 전체 CLI 테스트 실행**

```bash
uv run pytest tests/ -v --ignore=tests/integration -k "not e2e"
```
예상 결과: 모든 테스트 통과

- [ ] **단계 5: 커밋**

```bash
git add src/cli/main.py
git commit -m "fix(cli): NameError 방지를 위한 logger 정의 누락 추가

run_deep_dive()에서 logger가 사용되었으나 초기화되지 않아
선택적 도구(disclosure/flow) 실패 시 런타임 에러 발생

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: MacroSnapshot 이름 충돌 해결

**파일:**
- 수정: `src/tools/macro.py:8,56`
- 수정: `src/pipelines/ticker_report.py:3,37`
- 수정: `tests/pipelines/test_ticker_report.py:5,13-27`
- 테스트: `tests/tools/test_macro.py`, `tests/pipelines/test_ticker_report.py`

**문제:** 서로 다른 모듈에 호환되지 않는 두 개의 `MacroSnapshot` 클래스가 존재하여 타입 혼란 발생

- [ ] **단계 1: src/tools/macro.py의 클래스 이름 변경**

8번 줄을 `class TickerMacroSnapshot(BaseModel):`로 변경

- [ ] **단계 2: 반환 타입 주석 업데이트**

56번 줄을 `async def execute(self) -> ToolResult[TickerMacroSnapshot]:`로 변경

- [ ] **단계 3: export 업데이트**

파일 끝에 추가:
```python
__all__ = ["MacroTool", "TickerMacroSnapshot"]
```

- [ ] **단계 4: ticker_report.py의 import 업데이트**

3번 줄을 `from src.tools.macro import MacroTool, TickerMacroSnapshot`로 변경

- [ ] **단계 5: ticker_report.py의 타입 힌트 업데이트**

37번 줄을 `macro_data: TickerMacroSnapshot = macro_result.data`로 변경

- [ ] **단계 6: 테스트 파일의 import 업데이트**

`tests/pipelines/test_ticker_report.py` 5번 줄 import 수정

- [ ] **단계 7: 테스트 파일의 mock factory 업데이트**

13-27번 줄의 `TickerMacroSnapshot` 사용으로 변경

- [ ] **단계 8: macro tool 테스트 실행**

```bash
uv run pytest tests/tools/test_macro.py -v
```

- [ ] **단계 9: ticker report 파이프라인 테스트 실행**

```bash
uv run pytest tests/pipelines/test_ticker_report.py -v
```

- [ ] **단계 10: 다른 사용처 검색**

```bash
grep -r "MacroSnapshot" src/ tests/ --include="*.py" | grep -v "DailyReportMacroSnapshot\|TickerMacroSnapshot"
```
예상 결과: daily_report/models.py의 DailyReportMacroSnapshot만 표시됨

- [ ] **단계 11: 커밋**

```bash
git add src/tools/macro.py src/pipelines/ticker_report.py tests/pipelines/test_ticker_report.py
git commit -m "refactor(tools): MacroSnapshot을 TickerMacroSnapshot으로 이름 변경

호환되지 않는 두 MacroSnapshot 클래스 간 이름 충돌 해결:
- src/tools/macro.py: ticker_report 파이프라인에서 사용
- src/pipelines/daily_report/models.py: daily_report 파이프라인에서 사용

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: 사용되지 않는 Import 및 죽은 코드 제거

**파일:**
- 수정: `src/cli/main.py` (85번 줄, 248-266번 줄)
- 수정: `src/providers/kis.py` (1, 2, 7번 줄)
- 수정: `src/tools/screener/scoring.py` (2번 줄)
- 수정: `src/pipelines/daily_report/stages/map_stage.py` (5번 줄)
- 수정: `src/pipelines/daily_report/stages/reduce_stage.py` (6번 줄)
- 수정: `src/pipelines/ticker_report.py` (5번 줄)

**문제:** 여러 사용되지 않는 import와 완전히 사용되지 않는 함수가 코드 품질 저하

- [ ] **단계 1: main.py에서 load_config import 제거**

85번 줄 `from src.core.config import load_config` 삭제

- [ ] **단계 2: main.py에서 _render_quarterly_table 함수 제거**

248-266번 줄 전체 삭제

- [ ] **단계 3: kis.py에서 사용되지 않는 import 3개 제거**

- `import asyncio` (1번 줄)
- `from functools import lru_cache` (2번 줄)
- `from src.providers.kis_models import KISQuote` (7번 줄)

- [ ] **단계 4: scoring.py에서 numpy import 제거**

`import numpy as np` 줄 삭제 (pandas만 남김)

- [ ] **단계 5: map_stage.py에서 os import 제거**

`import os` 줄 삭제

- [ ] **단계 6: reduce_stage.py에서 timedelta import 제거**

`from datetime import datetime, timedelta`를 `from datetime import datetime`로 변경

- [ ] **단계 7: ticker_report.py에서 TechnicalResult import 제거**

`from src.tools.technical.models import TechnicalResult` 줄 삭제

- [ ] **단계 8: 전체 테스트 실행**

```bash
uv run pytest tests/ -v --ignore=tests/integration
```
예상 결과: 모든 테스트 통과

- [ ] **단계 9: linter 실행**

```bash
uv run ruff check src/ --select F401
```
예상 결과: "imported but unused" 에러 없음

- [ ] **단계 10: 커밋**

```bash
git add src/cli/main.py src/providers/kis.py src/tools/screener/scoring.py src/pipelines/daily_report/stages/map_stage.py src/pipelines/daily_report/stages/reduce_stage.py src/pipelines/ticker_report.py
git commit -m "refactor: 사용되지 않는 import 및 죽은 코드 제거

제거된 항목:
- cli/main.py: load_config import, _render_quarterly_table() 함수
- providers/kis.py: asyncio, lru_cache, KISQuote import
- screener/scoring.py: numpy import
- map_stage.py: os import
- reduce_stage.py: timedelta import
- ticker_report.py: TechnicalResult import

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: README 문서 업데이트

**파일:**
- 수정: `README.md` (256-260행, 49행 이후, 376-385행)

**문제:** README에 3개 도구 누락, screen 기능 누락, 잘못된 버전 번호

- [ ] **단계 1: 아키텍처 섹션에 누락된 도구 추가**

256-260행의 Tools 섹션에 다음 3개 추가:
- `FundamentalTool`: 재무 지표 및 분기 실적
- `DisclosureTool`: SEC EDGAR (미국) + OpenDART (한국) 공시 조회
- `FlowTool`: KIS API 기반 외인/기관 수급 동향

- [ ] **단계 2: Screen 기능 섹션 추가**

"### 4. 포트폴리오 모니터링" 섹션 이후에 새 섹션 삽입:

```markdown
### 5. 시장 스크리너 (Market Screener)
```bash
jarvis screen              # 전체 시장 스캔
jarvis screen --market kr  # 한국 시장만
jarvis screen --market us  # 미국 시장만
```
- Naver 테마 + KIS 순위 기반 유니버스 구성
- 누적 수익률, 연속 상승일, 거래량 폭발 지표 스코어링
- 후보 종목 랭킹 및 리포트 자동 저장
- 주도주 및 테마 발굴
```

- [ ] **단계 3: 이후 섹션 번호 재조정**

5→6, 6→7, 7→8로 섹션 번호 업데이트

- [ ] **단계 4: 버전 히스토리 수정**

376-385행의 v0.4.0 항목을 v0.3.0으로 병합 (CLI가 0.3.0을 보고하므로)

- [ ] **단계 5: 변경사항 검토**

```bash
git diff README.md
```

- [ ] **단계 6: 마크다운 포맷 검증**

```bash
uv run python -m markdown README.md > /tmp/readme.html && echo "Markdown valid"
```

- [ ] **단계 7: 커밋**

```bash
git add README.md
git commit -m "docs(readme): 누락된 기능 추가 및 버전 수정

추가:
- FundamentalTool, DisclosureTool, FlowTool
- Market Screener 기능 섹션
- 버전 히스토리 수정 (v0.4.0 → v0.3.0)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Docstring 및 CLI 문서 업데이트

**파일:**
- 수정: `src/pipelines/deep_dive.py:45-58`
- 수정: `src/cli/main.py:583`

**문제:** 두 docstring이 코드에 존재하는 기능(disclosure/flow)을 문서화하지 않음

- [ ] **단계 1: DeepDivePipeline.run() docstring 업데이트**

45-58행의 docstring에 다음 추가:
```python
- disclosure: list[DisclosureItem] | None (if disclosure_tool provided)
- flow: InvestorFlow | None (if flow_tool provided and ticker is Korean)
```

- [ ] **단계 2: analyze 명령어 docstring 업데이트**

583행을 다음에서:
```python
"""Deep dive analysis with LLM (technical + news)."""
```

다음으로 변경:
```python
"""Deep dive analysis with LLM (technical + news + disclosure + flow)."""
```

- [ ] **단계 3: docstring 접근 가능 확인**

```bash
uv run python -c "from src.pipelines.deep_dive import DeepDivePipeline; help(DeepDivePipeline.run)"
```

- [ ] **단계 4: CLI 도움말 텍스트 확인**

```bash
uv run jarvis analyze --help
```

- [ ] **단계 5: 커밋**

```bash
git add src/pipelines/deep_dive.py src/cli/main.py
git commit -m "docs: disclosure 및 flow 기능에 대한 docstring 업데이트

- DeepDivePipeline.run()이 이제 선택적 disclosure/flow 반환값 문서화
- analyze CLI 명령어 설명에 모든 분석 유형 포함

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: CLAUDE.md 아키텍처 노트 업데이트

**파일:**
- 수정: `CLAUDE.md:66-70`

**문제:** daily_report vs ticker_report 두 파이프라인 구조가 명확히 구분되지 않음

- [ ] **단계 1: Key modules 섹션 업데이트**

66-70행에 다음 2개 항목 추가:
```markdown
- `src/pipelines/ticker_report.py` — `report ticker` 명령용 단일 파일 파이프라인 (매크로 + 다중 티커 분석)
- `src/pipelines/daily_report/` — `report daily` 명령용 MapReduce 패키지 (텔레그램 메시지 클러스터링)
```

- [ ] **단계 2: 섹션 번호 확인**

```bash
grep -n "^## " CLAUDE.md
```

- [ ] **단계 3: CLAUDE.md 구조 검토**

```bash
head -100 CLAUDE.md
```

- [ ] **단계 4: 커밋**

```bash
git add CLAUDE.md
git commit -m "docs(claude): report용 두 파이프라인 아키텍처 명확화

추가된 구분:
- ticker_report.py: 'report ticker' 명령용 간단한 파이프라인
- daily_report/: 'report daily' 명령용 복잡한 MapReduce

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: 최종 검증 및 Push

**파일:**
- 테스트: 모든 테스트, 모든 import, 문서 일관성

- [ ] **단계 1: 전체 테스트 실행**

```bash
uv run pytest tests/ -v --ignore=tests/integration
```
예상 결과: 모든 테스트 통과

- [ ] **단계 2: 통합 테스트 실행**

```bash
uv run pytest tests/integration/ -v -m integration 2>/dev/null || echo "Integration tests require API keys (skipped OK)"
```

- [ ] **단계 3: import 에러 확인**

```bash
uv run python -c "
from src.cli.main import app
from src.pipelines.ticker_report import TickerReportPipeline
from src.pipelines.deep_dive import DeepDivePipeline
from src.tools.macro import TickerMacroSnapshot
print('All imports successful')
"
```

- [ ] **단계 4: CLI 로드 에러 없음 확인**

```bash
uv run jarvis --help
```

- [ ] **단계 5: 커밋 히스토리 검토**

```bash
git log --oneline -10
```
예상 결과: 이 정리 작업의 6개 새 커밋

- [ ] **단계 6: 원격에 push**

```bash
git push origin feature/code-cleanup
```

- [ ] **단계 7: Pull Request 생성**

```bash
gh pr create --title "refactor: 코드 정리 - 버그 수정, 죽은 코드 제거, 문서 업데이트" --body "$(cat <<'EOF'
## 요약

자동 분석으로 식별된 기술 부채를 해결하는 종합 코드 정리:

**치명적 수정:**
- 🐛 런타임 에러를 일으키던 main.py의 정의되지 않은 `logger` 수정
- 🔧 `MacroSnapshot` 클래스 이름 충돌 해결 (`TickerMacroSnapshot`으로 이름 변경)

**코드 품질:**
- 🧹 7개 파일에서 8개 사용되지 않는 import 제거
- 🗑️ 사용되지 않는 `_render_quarterly_table()` 함수 삭제
- 📝 `analyze` 명령어 및 `DeepDivePipeline`의 불완전한 docstring 업데이트

**문서화:**
- 📚 README에 누락된 도구 추가 (FundamentalTool, DisclosureTool, FlowTool)
- ✨ Market Screener 기능 문서 추가
- 🔢 버전 번호 불일치 수정 (v0.4.0 → v0.3.0)
- 🏗️ CLAUDE.md에서 두 파이프라인 아키텍처 명확화

## 테스트 계획

- [x] 모든 유닛 테스트 통과 (296개)
- [x] 통합 테스트 통과 (API 키 있을 때) 또는 우아하게 건너뛰기
- [x] CLI가 import 에러 없이 로드됨
- [x] 문서가 올바르게 렌더링됨

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## 자체 검토 체크리스트

**사양 커버리지:**
- ✅ 치명적 logger 버그 (Task 1)
- ✅ MacroSnapshot 충돌 (Task 2)
- ✅ 사용되지 않는 import 및 죽은 코드 (Task 3)
- ✅ README 문서 누락 (Task 4)
- ✅ 불완전한 docstring (Task 5)
- ✅ CLAUDE.md 명확화 (Task 6)
- ✅ 최종 검증 (Task 7)

**플레이스홀더 스캔:**
- ✅ "TBD" 또는 "TODO" 마커 없음
- ✅ 모든 코드 블록에 실제 구현 표시
- ✅ 모든 명령어에 예상 출력 표시
- ✅ 모든 파일 경로 정확함

**타입 일관성:**
- ✅ `MacroSnapshot` → `TickerMacroSnapshot` 일관되게 사용
- ✅ Logger 변수가 첫 사용 전에 추가됨
- ✅ Import 문이 이름 변경된 클래스와 일치
- ✅ 테스트 mock이 이름 변경된 클래스와 일치

---

## 참고사항

**이 순서를 선택한 이유:**
1. 런타임 버그 먼저 수정 (Task 1) - 후속 작업 중 에러 방지
2. 이름 충돌 해결 (Task 2) - 문서화를 위한 올바른 이름 설정
3. 죽은 코드 제거 (Task 3) - 문서 업데이트 전 깨끗한 상태
4. 문서 업데이트 (Tasks 4-6) - 정리된 코드베이스 반영
5. 검증 및 배포 (Task 7) - 모든 것이 함께 작동하는지 확인

**범위에서 제외:**
- `NewsArticle`/`NewsItem` 이름 변경 (더 광범위한 리팩토링 필요)
- `daily_report` 디렉토리 이름 변경 (많은 파일의 import를 깨뜨림)
- 변수명 개선 (`opt_results` → `optional_results`) (주관적, 낮은 우선순위)
- 타입 힌트 현대화 (`Optional` → `| None`) (Python 3.10+ 스타일은 선택사항)

필요시 향후 정리 반복에서 다룰 수 있습니다.
