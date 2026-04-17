# 코드 품질 유지 가이드

invest-jarvis 프로젝트의 코드 품질을 지속적으로 유지하기 위한 가이드입니다.

## 개요

코드가 낡지 않게 유지하기 위해서는:
1. **자동화된 검증** (CI/CD, pre-commit hooks)
2. **개발 프로세스** (PR 체크리스트, 정기 점검)
3. **명확한 규칙** (문서화, 네이밍)

---

## 1. 자동화된 검증

### 1.1 로컬 개발 환경

#### Pre-commit Hooks 설치

```bash
# 설치
uv sync --dev
uv run pre-commit install

# 수동 실행
uv run pre-commit run --all-files
```

설치 후 git commit 시 자동으로 실행됩니다:
- `ruff check --fix`: import 정리, unused variables 제거
- `ruff format`: 코드 포맷팅

#### 로컬 위생 점검

```bash
# PR 전에 실행 (필수)
./scripts/check_hygiene.sh
```

점검 항목:
- ✅ Ruff check (imports, code quality)
- ✅ Ruff format (코드 스타일)
- ⚠️  Vulture (unused code detection, 참고용)
- ✅ Unit tests (integration 제외)

### 1.2 CI/CD (GitHub Actions)

PR 생성/업데이트 시 자동 실행:
- `.github/workflows/code-quality.yml`
- Ruff check/format
- Vulture (unused code 탐지)
- Unit test suite

**PR merge 조건**: 모든 CI 체크 통과 필수

---

## 2. 개발 프로세스

### 2.1 PR 체크리스트

PR 생성 전 확인사항:

- [ ] `./scripts/check_hygiene.sh` 실행 및 통과
- [ ] 새 기능/수정사항에 대한 테스트 추가
- [ ] 관련 문서 업데이트 (README.md, CLAUDE.md, CLI_USAGE.md)
- [ ] 커밋 메시지가 conventional commits 형식 준수
- [ ] Unused imports/variables 없음
- [ ] Dead code 제거

### 2.2 코드 리뷰 기준

**Reviewer 체크리스트:**

1. **코드 품질**
   - Unused imports가 없는가?
   - Dead code가 없는가?
   - 변수/함수명이 명확한가?
   - 중복 코드가 없는가?

2. **테스트**
   - 새 기능에 대한 테스트가 있는가?
   - Edge case를 커버하는가?
   - Mock이 과도하지 않은가?

3. **문서**
   - README.md가 최신인가?
   - Docstring이 충분한가?
   - CLAUDE.md가 업데이트되었는가?

4. **아키텍처**
   - 레이어 분리가 명확한가?
   - 의존성 방향이 올바른가?
   - SOLID 원칙을 따르는가?

### 2.3 정기 점검 (월 1회 권장)

```bash
# 1. 전체 lint 실행
uv run --group dev ruff check src tests

# 2. Unused code 탐지
uv run --group dev vulture src --min-confidence 80

# 3. 테스트 커버리지 확인
uv run pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html

# 4. 문서 sync 확인
# - README.md의 Features vs 실제 CLI commands
# - CLAUDE.md의 Tools vs src/tools/ 디렉토리
# - CLI_USAGE.md vs src/cli/main.py의 commands
```

---

## 3. 코딩 규칙

### 3.1 Import 관리

**좋은 예:**
```python
# Standard library
import asyncio
import logging
from pathlib import Path

# Third-party
import typer
from rich.console import Console

# Local
from src.tools.technical import TechnicalAnalysisTool
from src.providers.yfinance_provider import YFinanceProvider

logger = logging.getLogger(__name__)
```

**나쁜 예:**
```python
from src.tools.technical import *  # Wildcard import
import unused_module  # Unused import
from src.tools.fundamental import FundamentalTool, QuarterlyData  # QuarterlyData 안 쓰면 제거
```

### 3.2 Dead Code 관리

**규칙:**
- 사용하지 않는 함수는 즉시 삭제 (주석 처리 금지)
- TODO 주석은 GitHub Issue로 변환
- 임시 코드는 최대 1주일 내 제거

**나쁜 예:**
```python
# def old_implementation():
#     # TODO: remove this later
#     pass

def _render_quarterly_table():  # 호출되지 않는 함수
    pass
```

### 3.3 네이밍 규칙

**명확한 이름 사용:**
```python
# 좋은 예
class TickerMacroSnapshot:  # 단일 종목용 macro snapshot
class MacroSnapshot:  # 일일 리포트용 macro snapshot

# 나쁜 예
class MacroSnapshot:  # 어디에 쓰는 건지 불분명
class MacroSnapshot2:  # 숫자로 구분 금지
```

**Private 함수 명확히:**
```python
def _format_metric_value():  # Private helper
    pass

def format_output():  # Public interface
    pass
```

### 3.4 문서화 규칙

**Docstring 작성:**
```python
def run(self, ticker: str) -> dict:
    """Run deep dive analysis for a ticker.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', '005930.KS')

    Returns:
        dict with keys:
            - technical: TechnicalResult
            - fundamental: FundamentalSnapshot | None
            - news: list[NewsArticle]
            - disclosure: list[DisclosureItem] | None
            - flow: InvestorFlow | None

    Raises:
        ValueError: If ticker is invalid
        RuntimeError: If analysis fails
    """
```

**변경 시 문서 업데이트:**
- 새 CLI 명령어 → `docs/CLI_USAGE.md`
- 새 파이프라인/툴 → `README.md` + `CLAUDE.md`
- 아키텍처 변경 → `CLAUDE.md`

---

## 4. 도구 설정

### 4.1 Ruff 설정 (pyproject.toml)

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "UP",  # pyupgrade
    "B",   # flake8-bugbear
]
ignore = [
    "E501",  # Line too long (handled by formatter)
]

[tool.ruff.lint.isort]
known-first-party = ["src"]
```

### 4.2 Vulture 설정

```python
# vulture_whitelist.py (필요 시)
# 의도적으로 사용하지 않는 코드 (프레임워크 요구사항 등)

# Typer CLI entry points
check  # Used by Typer
analyze  # Used by Typer
report  # Used by Typer
```

---

## 5. 트러블슈팅

### "Ruff check fails with import errors"

```bash
# Import 순서 자동 수정
uv run --group dev ruff check --fix src tests
```

### "Vulture reports false positives"

Vulture는 참고용입니다. 다음은 무시해도 됩니다:
- Typer command decorators로 정의된 함수
- Pydantic model fields
- `__init__.py`의 `__all__` exports

실제 unused code인지 확인:
```bash
# 해당 심볼이 어디서 사용되는지 검색
uv run --group dev ruff check --select F401,F841  # Unused imports/variables만
```

### "Tests fail after cleanup"

```bash
# 변경된 파일만 테스트
uv run pytest tests/path/to/test_file.py -v

# 실패한 테스트만 재실행
uv run pytest --lf
```

---

## 6. 예방 체크리스트

### 개발 시작 전
- [ ] 최신 main branch pull
- [ ] Pre-commit hooks 설치 확인

### 개발 중
- [ ] 새 import 추가 시 실제로 사용하는지 확인
- [ ] 함수 삭제 시 호출처 모두 제거
- [ ] 이름 변경 시 모든 참조 업데이트 (IDE refactoring 사용)

### PR 생성 전
- [ ] `./scripts/check_hygiene.sh` 실행
- [ ] 문서 업데이트 확인
- [ ] Self-review (GitHub "Files changed" 탭)

### PR 머지 후
- [ ] 로컬 브랜치 삭제
- [ ] main branch pull & 최신화

---

## 7. 참고 자료

### 내부 문서
- [CLAUDE.md](../CLAUDE.md) - 아키텍처 가이드
- [CLI_USAGE.md](./CLI_USAGE.md) - CLI 사용법
- [README.md](../README.md) - 프로젝트 개요

### 외부 문서
- [Ruff Rules](https://docs.astral.sh/ruff/rules/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Python PEP 8](https://peps.python.org/pep-0008/)

---

## 8. 요약

**매일:**
- Pre-commit hooks가 자동으로 실행되도록 설정

**PR 생성 시:**
- `./scripts/check_hygiene.sh` 실행 필수

**월 1회:**
- 전체 프로젝트 vulture 스캔
- 문서 sync 확인

**원칙:**
- "삭제하기 쉬운 코드가 좋은 코드"
- "문서는 코드와 함께 업데이트"
- "자동화할 수 있으면 자동화"
