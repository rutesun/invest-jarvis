# Map Stage Prompt Evaluation

Daily report pipeline의 Map stage 프롬프트 품질 평가 시스템입니다.

## Quick Start

```bash
# 로컬 평가
uv run python evaluations/evaluate_map.py

# LangSmith 연동
uv run python evaluations/langsmith_eval.py --experiment v4
```

## 상세 가이드

전체 평가 시스템 문서: [@docs/EVALUATION.md](../docs/EVALUATION.md)

- 평가 메트릭 설명
- 테스트 케이스 추가 방법
- 프롬프트 버전 관리
- 문제 해결 가이드
