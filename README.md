# Invest-Jarvis

Korean/US 주식 투자 분석 CLI 도구

## 주요 기능

| 기능 | 명령어 | 설명 |
|------|--------|------|
| **Quick Check** | `jarvis check AAPL` | LLM 없이 빠른 기술적 분석 (5-전략 시스템) |
| **Deep Dive** | `jarvis analyze AAPL` | 기술 + 뉴스 + LLM 종합 분석 |
| **Daily Report** | `jarvis report daily` | 텔레그램 기반 브리프 + 리서치 덤프 + 운영 QA 리포트 |
| **Portfolio** | `jarvis portfolio` | KIS API 포트폴리오 모니터링 |
| **Screener** | `jarvis screen` | 시장 스크리닝 (Naver + KIS 랭킹) |
| **Telegram** | `jarvis telegram fetch` | 텔레그램 채널 메시지 수집 |
| **Cache** | `jarvis cache list` | 티커 캐시 관리 |
| **Evaluation** | `python evaluations/evaluate_map.py` | 프롬프트 품질 평가 |

**상세 가이드**:
- CLI 사용법: [@docs/CLI_USAGE.md](docs/CLI_USAGE.md)
- 평가 시스템: [@docs/EVALUATION.md](docs/EVALUATION.md)

---

## Quick Start

```bash
# 1. 설치
uv sync

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일 편집 (OPENAI_API_KEY 등)

# 3. 실행
uv run jarvis check AAPL
uv run jarvis analyze AAPL
uv run jarvis report
```

**개발 문서**:
- 설치 및 설정: [@docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
- 아키텍처: [@docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## 라이선스

MIT

---
