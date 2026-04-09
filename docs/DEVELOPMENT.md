# 개발 가이드

## 개발 환경 설정

### 요구사항
- Python 3.12+
- uv (패키지 관리자)

### 초기 설정
```bash
# 저장소 클론
git clone <repo-url>
cd invest-jarvis

# 의존성 설치
uv sync --all-extras

# 개발 모드 설치
uv pip install -e .

# 환경 변수 설정
cp .env.example .env
# .env 파일 편집
```

---

## 프로젝트 구조

```
invest-jarvis/
├── src/
│   ├── core/              # 핵심 인터페이스 및 설정
│   ├── providers/         # 데이터 제공자
│   ├── tools/             # 분석 도구
│   │   └── technical/     # 기술적 분석
│   ├── llm/               # LLM 클라이언트
│   ├── pipelines/         # 워크플로우
│   └── cli/               # CLI 진입점
├── tests/                 # 테스트
└── docs/                  # 문서
```

---

## 테스트

### 유닛 테스트
```bash
# 전체 실행
uv run pytest tests/ -v --ignore=tests/integration

# 특정 모듈
uv run pytest tests/tools/technical/ -v
```

### 통합 테스트
```bash
export OPENAI_API_KEY=sk-...
uv run pytest tests/integration/ -v -m integration
```

### 커버리지
```bash
uv run pytest tests/ --cov=src --cov-report=html --ignore=tests/integration
open htmlcov/index.html
```

---

## 새 전략 추가

### 1. 전략 클래스 작성
`src/tools/technical/strategies/my_strategy.py`

### 2. 레지스트리에 등록
`src/tools/technical/registry.py`의 `STRATEGY_MAP`

### 3. 설정 추가
`config.yaml`의 `strategies` 리스트

### 4. 테스트 작성
`tests/tools/technical/test_my_strategy.py`

---

## 코딩 스타일

- 타입 힌트 필수
- Pydantic 모델 사용
- Async/Await 사용
- 명확한 에러 처리

---

## Git 워크플로우

```bash
# Feature 브랜치
git checkout -b feature/my-feature

# 커밋
git commit -m "feat: add my feature"

# Push
git push origin feature/my-feature
```

커밋 메시지:
- `feat:` - 새 기능
- `fix:` - 버그 수정
- `docs:` - 문서
- `test:` - 테스트
- `refactor:` - 리팩토링
