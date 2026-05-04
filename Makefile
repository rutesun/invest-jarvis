.PHONY: help check analyze portfolio screen daily quick-scan catchup upload
.DEFAULT_GOAL := help

# Variables
JARVIS := uv run jarvis
DATE ?= $(shell date '+%Y-%m-%d')
MARKET ?= all

help:
	@echo "📊 invest-jarvis Commands"
	@echo ""
	@echo "📈 Analysis:"
	@echo "  make check TICKER=AAPL       빠른 체크"
	@echo "  make analyze TICKER=AAPL     심층 분석 (기술+뉴스+LLM)"
	@echo "  make portfolio               포트폴리오 모니터링"
	@echo "  make quick-scan              주요 3종목 빠른 체크"
	@echo ""
	@echo "📰 Workflows:"
	@echo "  make daily                   텔레그램 수집 → 리포트 → Notion (오늘)"
	@echo "  make daily DATE=2026-04-17   특정 날짜"
	@echo ""
	@echo "  make screen                  시장 스크리너 → Notion (전체)"
	@echo "  make screen MARKET=kr        한국 시장만"
	@echo ""
	@echo "🔧 Utilities:"
	@echo "  make catchup                 텔레그램 누락분 보충"
	@echo "  make upload                  기존 리포트 Notion 업로드"

# ============================================================================
# Analysis Commands
# ============================================================================

check:  ## 빠른 기술적 분석
	@if [ -z "$(TICKER)" ]; then \
		echo "❌ TICKER를 지정하세요: make check TICKER=AAPL"; \
		exit 1; \
	fi
	@$(JARVIS) check $(TICKER)

analyze:  ## 심층 분석 (기술+뉴스+LLM)
	@if [ -z "$(TICKER)" ]; then \
		echo "❌ TICKER를 지정하세요: make analyze TICKER=AAPL"; \
		exit 1; \
	fi
	@$(JARVIS) analyze $(TICKER)

portfolio:  ## 포트폴리오 모니터링
	@$(JARVIS) portfolio

quick-scan:  ## 주요 3종목 빠른 체크
	@echo "🔍 주요 종목 체크 (AAPL, MSFT, NVDA)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@$(JARVIS) check AAPL
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@$(JARVIS) check MSFT
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@$(JARVIS) check NVDA

# ============================================================================
# Workflow Commands
# ============================================================================

daily:  ## 텔레그램 수집 → 일일 리포트 → Notion
	@echo "📅 날짜: $(DATE)"
	@echo "📥 텔레그램 메시지 수집..."
	@$(JARVIS) telegram fetch $(DATE)
	@echo ""
	@echo "📊 리포트 생성 + Notion 업로드..."
	@$(JARVIS) report daily $(DATE) --notion
	@echo ""
	@echo "✅ 완료: reports/$$(echo $(DATE) | cut -d- -f1-2)/daily_$(DATE).md + Notion"

screen:  ## 시장 스크리너 + Notion
	@echo "🔍 스크리너 실행 (시장: $(MARKET))..."
	@$(JARVIS) screen --market $(MARKET) --notion
	@echo "✅ 완료"

# ============================================================================
# Utilities
# ============================================================================

catchup:  ## 텔레그램 누락분 보충
	@$(JARVIS) telegram catch-up

upload:  ## 기존 리포트 Notion 일괄 업로드
	@$(JARVIS) report upload
