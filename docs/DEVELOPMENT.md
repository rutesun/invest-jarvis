# 개발 가이드

## 개발 환경 설정

### 요구사항
- Python 3.12+
- uv

### 설치
```bash
# 의존성 설치
uv sync

# 개발 의존성 포함
uv sync --dev

# editable 모드 설치
uv pip install -e .
```

### 환경 변수
`.env` 파일 생성:
```bash
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
KIS_APP_KEY=...
KIS_APP_SECRET=...
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
```

---

## 코드 설계 원칙

**적용 원칙**:
- Martin Fowler: 코드 스멜 제거, 작은 리팩토링, 명확한 의도
- Robert C. Martin (SOLID): 단일 책임, 의존성 방향 일관성
- Kent Beck: 가장 단순한 설계, 중복 제거, 테스트 가능성
- Michael Feathers: 테스트 가능한 경계(seam) 생성
- DDD (해당 시): 도메인 모델과 유비쿼터스 언어 일관성

**코드 스타일**:
- 하드코딩 금지: config/utilities 사용
- Clean code: TODO 코멘트 금지, 미사용 코드는 완전 삭제
- 일관된 네이밍: JS는 camelCase, Python은 snake_case
- 주석 플레이스홀더 금지: 코드 삭제 시 주석 남기지 않기

**핵심 요구사항**:
1. 직접적 접근: 우회/임시 솔루션 금지
2. 완전한 구현: TODO 남기지 말고 완성하거나 하지 말기
3. 성능 우선: 메모리 누수, CPU 사용, 스레드 블로킹 고려
4. 빌드 검증: 모든 warning/error 해결 후 진행
5. 파일 분리 우선: 새 기능은 새 파일에
6. 비판적 사고: 사용자 요청에 대해 trade-off 고려

---

## 테스트

### 실행
```bash
# 전체 테스트
uv run pytest

# 커버리지 포함
uv run pytest --cov=src

# 특정 파일
uv run pytest tests/tools/test_technical.py

# 특정 테스트
uv run pytest tests/tools/test_technical.py::test_trend_strategy
```

### 테스트 작성 원칙
- 단위 테스트: 각 함수/메서드 독립 검증
- 통합 테스트: 파이프라인 전체 흐름
- Fixture 활용: `conftest.py`에 공통 fixture
- Mock 사용: 외부 API 호출은 mock

---

## 문서화 규칙

**모든 구현 작업 시 반드시 준수**:

| 변경 | 업데이트 문서 |
|------|---------------|
| 새 기능/파이프라인 추가 | `README.md` Features 섹션 |
| 새 CLI 커맨드 추가 | `docs/CLI_USAGE.md` Commands 섹션 |
| 새 모듈/패키지 추가 | `docs/` 아래 대응 문서 |
| 아키텍처 변경 | `docs/ARCHITECTURE.md` |
| 의존성 추가 | `README.md` 설치/설정 섹션 |

**문서 업데이트는 코드 변경과 같은 커밋에 포함.**

---

## Git 워크플로우

### 브랜치 전략
```bash
main                # 안정 버전
feature/*          # 새 기능
fix/*              # 버그 수정
```

### 커밋 메시지
```
<type>(<scope>): <subject>

feat: 새 기능
fix: 버그 수정
refactor: 리팩토링
docs: 문서 변경
test: 테스트 추가/수정
chore: 빌드/설정 변경
```

**예시**:
```
feat(evaluation): Map stage 프롬프트 평가 파이프라인 추가
fix(eval): category_accuracy Jaccard 유사도로 수정
docs: ARCHITECTURE.md 아키텍처 문서 추가
```

### Git Safety
- ❌ git config 수정 금지
- ❌ 파괴적 명령 금지 (push --force, reset --hard, checkout ., clean -f)
- ❌ 훅 스킵 금지 (--no-verify, --no-gpg-sign)
- ❌ main/master에 force push 금지
- ✅ 새 커밋 생성 (amend 대신)
- ✅ 특정 파일명으로 staging (git add -A 지양)

---

## Rollback 전략

**절대 사용 금지**:
- `git reset`
- `git revert`
- `git restore`
- `git checkout --`

**권장 방법**:
- 최근 변경사항을 수동으로 역변경
- Edit tool로 이전 내용 복원
- 현재 세션에서 변경한 내용 추적 후 되돌리기

---

## Skills 작성 규칙

**위치**: `.claude/skills/`

**규칙**:
- 단순 CLI 래퍼만
- 명령어 + 간단한 설명 + 예시
- 20줄 이하로 유지

**예시**:
```markdown
# jarvis-check

빠른 기술적 분석

## Usage
jarvis check AAPL

## Example
jarvis check AAPL
jarvis check 삼성전자
```

---

## 코드 리뷰 체크리스트

### 기능 구현
- [ ] 요구사항 충족
- [ ] 엣지 케이스 처리
- [ ] 에러 핸들링 적절
- [ ] 성능 고려 (메모리, CPU)

### 코드 품질
- [ ] SOLID 원칙 준수
- [ ] 함수/클래스 크기 적절
- [ ] 네이밍 명확
- [ ] 중복 코드 없음
- [ ] 하드코딩 없음

### 테스트
- [ ] 단위 테스트 작성
- [ ] 테스트 통과
- [ ] 커버리지 유지/향상

### 문서
- [ ] CLAUDE.md/README.md 업데이트 (필요시)
- [ ] 주석/docstring 추가 (복잡한 로직만)
- [ ] 변경사항 문서화

---

## 패키지 관리

**패키지 매니저**: `uv` (pip 직접 사용 금지)

### 의존성 추가
```bash
uv add package-name
uv add --dev pytest-package
```

### 의존성 동기화
```bash
uv sync
uv sync --all-extras
```

---

## 디버깅

### 로깅
```python
import logging
logger = logging.getLogger(__name__)

logger.debug("디버그 메시지")
logger.info("정보 메시지")
logger.warning("경고 메시지")
logger.error("에러 메시지")
```

### 브레이크포인트
```python
import pdb; pdb.set_trace()  # Python debugger
```

### VS Code 디버그 설정
`.vscode/launch.json`:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: jarvis",
      "type": "python",
      "request": "launch",
      "module": "src.cli.main",
      "args": ["check", "AAPL"],
      "console": "integratedTerminal"
    }
  ]
}
```
