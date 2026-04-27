# invest-jarvis Development Roadmap

> 📍 **Navigation:** [ROADMAP](ROADMAP.md) (You are here) ↔ [TODOS](TODOS.md)
> 
> 최종 업데이트: 2026-04-27
> 목표: "핵심 인사이트 부족" 문제 해결 → 명확한 투자 신호 제공

---

## 🎯 Current Focus (2026-04-27)

**진행 중:**
- Technical Component Enhancements Phase 1 (60% 완료)
  - 상세 작업: [TODOS.md](TODOS.md)

**다음 우선순위:**
1. Technical Component Phase 1 완료 (Pocket Pivot, Tennis Ball/Egg)
2. Actionable Signal Output 구현
3. Backtesting Engine 시작

---

## ✅ Completed

### 2026-04-27
- **Chart Visualization Enhancement** - PR #21
  - 6개 이동평균선 (MA10/20/50/120/150/200) with 사용자 색상 스키마
  - Supertrend 추세선 + 매수/매도 시그널 마커
  - cRSI 패널 (동적 밴드), MACD 패널 (빨강/초록 히스토그램)
  - Volume + MA50 오버레이
  - 다크 테마 (통일된 배경), MA 라벨 (y축 오른쪽 그룹화)
  - Stage2 음영, 지지/저항선, 차트 패턴 마커
  - **성과:** 19 commits, 94 tests passing, 코드 리뷰 98점

### 2026-04-25
- **VCP 2-Stage & Volume Patterns** - PR #20
  - VCP Strong/General 구분
  - 3개 새 거래량 패턴

### 2026-04-23
- **Technical Chart Visualization** - PR #19
  - 기본 차트 렌더링 및 성능 메트릭

---

## 🚧 In Progress

### Technical Component Enhancements (Phase 1)
**진행률:** 60% (3/5 core tasks done)  
**상세:** [TODOS.md](TODOS.md)

**완료:**
- [x] Chart Enhancement (PR #21)
- [x] VCP 2-Stage (PR #20)
- [x] Column name standardization

**남은 작업:**
- [ ] Pocket Pivot 구현
- [ ] Tennis Ball/Egg 패턴
- [ ] Power Gap Up 강화
- [ ] Score 재조정
- [ ] 단위/통합 테스트

---

## 📋 Planned

### Phase 1: Actionable Signal (1-2시간)

**목표:** "핵심 인사이트 부족" 문제 해결. 명확한 액션 + 구체적 근거 제공.

**작업 항목:**

| # | 작업 | 파일 | 예상 시간 | 우선순위 |
|---|------|------|-----------|----------|
| 1.1 | `ActionableSignalOutput` 모델 추가 | `src/llm/models.py` | 10분 | P0 |
| 1.2 | `generate_actionable_signal()` 함수 작성 | `src/llm/analyzer.py` | 30분 | P0 |
| 1.3 | 파이프라인 통합 (`actionable_signal` 반환) | `src/pipelines/deep_dive.py` | 15분 | P0 |
| 1.4 | CLI 출력 개선 (Rich Panel 박스) | `src/cli/main.py` | 20분 | P0 |
| 1.5 | 10개 종목 테스트 및 프롬프트 튜닝 | - | 30분 | P0 |

**완료 기준:**
- `jarvis analyze AAPL` 실행 시 박스 형태로 명확한 신호 출력
- headline: "지금 XXX해라. 이유: A + B" 형식
- timing: "지금" | "3일_기다림" | "조정_대기" | "보류" 중 하나
- signal_strength: 1-10 시각화 (🔥 이모지)
- primary_reason: 구체적 숫자 포함 (RSI 28, P/E 12 등)
- invalidation_point: stop-loss 가격 명시

**의존성:** 없음 (기존 코드 활용)

---

## Phase 2: Backtesting Engine (다음 - 3-4시간 CC 구현)

**목표:** "과거 결과 검증 불가" 문제 해결. 전략 정확도를 숫자로 증명.

**작업 항목:**

| # | 작업 | 파일 | 예상 시간 | 우선순위 |
|---|------|------|-----------|----------|
| 2.1 | 백테스팅 프레임워크 선택 (vectorbt vs 직접 구현) | - | 30분 | P1 |
| 2.2 | `BacktestConfig` 모델 (기간, 초기 자본 등) | `src/tools/backtest/models.py` | 15분 | P1 |
| 2.3 | `BacktestRunner` 클래스 구현 | `src/tools/backtest/runner.py` | 1시간 | P1 |
| 2.4 | 과거 데이터 다운로드 (yfinance, 60-180일) | `src/tools/backtest/data_loader.py` | 30분 | P1 |
| 2.5 | 정확도 측정 (precision, recall, Sharpe ratio) | `src/tools/backtest/metrics.py` | 30분 | P1 |
| 2.6 | CLI 커맨드 추가 (`jarvis backtest AAPL --days 60`) | `src/cli/main.py` | 20분 | P1 |
| 2.7 | 결과 CSV 저장 및 요약 출력 | - | 20분 | P1 |

**완료 기준:**
- `jarvis backtest AAPL --days 60` 실행 시:
  - 과거 60일 데이터로 전략 시뮬레이션
  - "정확도: 68% (25/37 신호)" 출력
  - "수익률: +12.3% (Buy & Hold: +8.1%)" 출력
  - CSV 저장: `backtest_results/AAPL_20260423.csv`

**의존성:** Phase 1 완료 필요 (`ActionableSignalOutput` 모델)

---

## Phase 3: Web Dashboard (그 다음 - 반나절 CC 구현)

**목표:** "CLI가 불편함" 문제 해결. 차트와 리포트를 웹에서 시각화.

**작업 항목:**

| # | 작업 | 파일/기술 | 예상 시간 | 우선순위 |
|---|------|-----------|-----------|----------|
| 3.1 | 프레임워크 선택 (Streamlit vs Gradio) | - | 15분 | P2 |
| 3.2 | 홈 페이지 (최근 분석 이력) | `dashboard/app.py` | 30분 | P2 |
| 3.3 | 종목 분석 페이지 (신호 + 차트) | `dashboard/pages/analyze.py` | 1시간 | P2 |
| 3.4 | 백테스트 결과 시각화 (plotly 차트) | `dashboard/pages/backtest.py` | 1시간 | P2 |
| 3.5 | 포트폴리오 모니터링 페이지 | `dashboard/pages/portfolio.py` | 45분 | P2 |
| 3.6 | Docker 이미지 생성 (배포용) | `Dockerfile` | 30분 | P2 |

**완료 기준:**
- `uv run streamlit run dashboard/app.py` 실행 시:
  - 종목 입력 → 신호 박스 + 기술 차트 표시
  - 백테스트 결과 → equity curve, drawdown 차트
  - 포트폴리오 → 보유 종목 + 손익 현황

**의존성:** Phase 1, 2 완료 (데이터 소스)

---

## Phase 4: Advanced Features (장기 - 선택적)

**목표:** 10배 버전. 매매 타이밍 예측, 포트폴리오 최적화, 리스크 경고, 섹터별 전략.

**작업 항목 (우선순위 순):**

| # | 기능 | 설명 | 예상 시간 | 우선순위 |
|---|------|------|-----------|----------|
| 4.1 | 리스크 경고 시스템 | 보유 종목 리스크 발생 시 알림 (Slack/Telegram) | 2시간 | P2 |
| 4.2 | 섹터별 전략 추천 | 반도체/이차전지/AI 섹터별 최적 전략 | 3시간 | P3 |
| 4.3 | 포트폴리오 최적화 | 보유 종목 분석 후 "이걸 팔고 저걸 사라" 추천 | 4시간 | P3 |
| 4.4 | 매매 타이밍 예측 (ML) | 과거 패턴 학습 → "3일 후 진입" 예측 | 1주 | P4 |
| 4.5 | 자동 매매 연동 (KIS API) | 신호 → 실제 주문 실행 (사용자 승인 필수) | 1주 | P4 |

**완료 기준:** 각 기능별로 별도 정의 필요

**의존성:** Phase 1-3 완료 + 충분한 백테스트 데이터

---

## Implementation Timeline (예상)

```
Week 1: Phase 1 완료 (즉시 사용 가능)
        ├─ Day 1-2: Actionable Signal 구현 + 테스트
        └─ Day 3-7: 실제 사용하며 프롬프트 튜닝

Week 2-3: Phase 2 완료 (정확도 증명)
          ├─ Week 2: Backtesting 엔진 구현
          └─ Week 3: 여러 종목/전략 백테스트 + 분석

Week 4-5: Phase 3 완료 (웹 대시보드)
          ├─ Week 4: Streamlit 앱 구현
          └─ Week 5: 차트 시각화 + Docker 배포

Week 6+: Phase 4 (선택적, 필요시)
         순차적으로 하나씩 추가
```

**Total:** 1-2개월 (1-2시간/일 작업 가정)

---

## Critical Path (핵심 경로)

```
Phase 1 (P0) → Phase 2 (P1) → Phase 3 (P2)
   ↓
즉시 사용 가능 → 정확도 증명 → 시각화
```

Phase 4는 **선택적**. Phase 1-3이 완료되면 이미 강력한 도구.

---

## Risk Mitigation (리스크 대응)

| 리스크 | 발생 가능성 | 영향 | 대응 방안 |
|--------|-------------|------|-----------|
| Phase 1 프롬프트가 여전히 모호함 | Medium | High | 10개 종목 실제 테스트 → 즉시 튜닝 |
| 백테스팅 프레임워크 선택 실패 | Low | Medium | vectorbt 시도 → 안 되면 직접 구현 |
| 과거 데이터 다운로드 느림 | Medium | Low | 캐싱 추가 (한번 받으면 저장) |
| 웹 대시보드 성능 문제 | Low | Medium | 차트 lazy loading, 결과 캐싱 |
| Phase 4 범위 과다 | High | Low | Phase 4는 선택적, 하나씩만 |

---

## Success Metrics (성공 지표)

**Phase 1:**
- 10개 종목 테스트 시 모두 3초 이내 응답
- headline 100% "지금 XXX. 이유: A + B" 형식
- primary_reason 100% 구체적 숫자 포함

**Phase 2:**
- 백테스트 정확도 측정 가능 (precision, recall)
- 10개 종목 60일 백테스트 < 5분
- Sharpe ratio > 1.0 전략 찾기

**Phase 3:**
- 웹 대시보드 첫 로딩 < 2초
- 차트 인터랙티브 (확대/축소 가능)
- 커뮤니티 공유 준비 (Docker 이미지)

**Phase 4:**
- 각 기능별로 별도 정의

---

## Design Document

상세 설계는 `~/.gstack/projects/rutesun-invest-jarvis/user-main-design-20260423-103958.md` 참조

---

## 다음 단계

1. **Phase 1 시작**: `ActionableSignalOutput` 모델부터 구현
2. **10개 종목 테스트**: AAPL, MSFT, NVDA, TSLA, GOOGL, META, 삼성전자, SK하이닉스, NAVER, 카카오
3. **프롬프트 튜닝**: 실제 결과 보고 개선
