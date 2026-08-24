# invest-jarvis Development Roadmap

> 최종 업데이트: 2026-04-29
>
> **사용법:** Task 하나 골라서 설계 → 구현 → 완료. 순서대로 할 필요 없음.
>
> **관련 문서:**
> - 설계: `~/.gstack/projects/rutesun-invest-jarvis/` (design docs)
> - 기능명세: `docs/FEATURES.md`
> - 아키텍처: `docs/ARCHITECTURE.md`

---

## ✅ Completed

### 2026-04-27: Chart Visualization Enhancement (PR #21)
6개 MA + Supertrend + cRSI/MACD 패널 + Stage2 음영 + 패턴 마커 + 지지/저항선. 94 tests passing.

### 2026-04-25: VCP 2-Stage & Volume Patterns (PR #20)
VCP Strong/General 구분. Pocket Pivot, Tennis Ball/Egg, Power Gap Up.

### 2026-04-25: Technical Component Enhancements (PR #20)
Score 재조정 완료. VCP Strong/General 차등화(20/10), Pocket Pivot(25), Tennis Ball(15), Egg(-15, 첫 음수), Power Gap Up(20). Column name standardization. 16개 새 테스트.

### 2026-04-23: Technical Chart Visualization (PR #19)
기본 차트 렌더링 및 성능 메트릭.

---

---

## 📋 Task 목록

### Task 1: 공시 원문 파싱 (Disclosure Intelligence) `P0`

**왜:**
`jarvis analyze AAPL` 실행하면 공시 **제목만** 나옴 (예: "[8-K] Material Contract Agreement").
"계약 금액이 얼마인지", "가이던스 상향/하향인지", "리스크가 뭔지" 전혀 모름.
지금은 ChatGPT에 10-K 원문 수동 복붙해서 분석 중. 귀찮고 자동화 필요.

**이미 완료된 부분:**
- ✅ `DisclosureTool` — SEC/DART 공시 **메타데이터** 수집 (`src/tools/disclosure.py`)
- ✅ `deep_dive.py` 파이프라인에 통합됨 (제목, 날짜, URL 출력)
- ✅ PR #8에서 구현됨

**남은 작업 (원문 파싱):**
- SEC edgartools로 10-K/10-Q XBRL 파싱 (핵심 숫자 자동 추출)
- `FilingFacts` 모델 (매출, 영업이익, FCF, Guidance, 리스크)
- XBRL concept mapping (회사마다 태그 다름 → fallback 체인)
- LLM으로 Guidance (Item 7) + Risk Factors (Item 1A) 추출
- QoQ/YoY 자동 비교 계산
- Rich Table로 숫자 테이블 CLI 출력
- Confidence scoring (XBRL=high, LLM=medium, 추정=low)
- 8-K Item 2.02 필터링 (실적 발표만 파싱)
- Golden set 테스트 (25개 종목, edge case 포함)
- Phase 1.2: DART 한국 공시 원문 파싱 추가

**상태:** 🟢 Ready (설계 완료, 인프라 존재)
**설계:** `~/.gstack/projects/rutesun-invest-jarvis/user-main-design-20260423-174653.md`
**예상:** 1-2일
**의존성:** 없음

---

### Task 2: Daily Report 프롬프트 개선 `P0`

**왜:**
Daily report가 **단순 요약** 수준.
"블룸 에너지가 계약 체결했다" → 끝.
"왜 이게 중요한가", "어떤 경로로 주가에 영향 주는가" 설명 없음.
결국 리포트는 키워드 목록이고, 실제 판단은 원문 읽고 내가 함.

**뭘:**
- Wrapup/Reduce 프롬프트 V4 작성 (`prompts.py`)
- 인과관계 3단계 체인 요구 명시: "A → B → C → 주가 영향"
- 각 연결고리마다 "왜?" 명시 의무화
- "단순 나열 금지, 논리적 흐름 필수" 지시
- Few-shot 예시 추가 (좋은 체인 3개 + 나쁜 체인 2개)
- 3-5일 실전 테스트 → 리포트만으로 투자 판단 가능한지 확인
- 판단 기준: 원문 안 봐도 되면 성공 / 여전히 원문 봐야 하면 Task 3으로

**상태:** 🟢 Ready
**Change record:** [`docs/changes/daily-report-causal-reasoning.md`](changes/daily-report-causal-reasoning.md)
**예상:** 2-3시간 (프롬프트) + 3-5일 (실전 테스트)
**의존성:** 없음

---

### Task 3: Chain 스테이지 (인과관계 엔진) `P1`

**왜:**
Task 2 (프롬프트 개선)로 부족할 때만 진행.
프롬프트만으로는 LLM이 지시를 놓치거나 얕은 체인을 만들 수 있음.
별도 스테이지로 분리하면: 체인 생성 → 자기비판 → 검증의 2단계 프로세스 가능.

**뭘:**
- 새 `chain_stage.py` 추가 (Reduce → **Chain** → Wrapup)
- Reduce 출력 (`NewsItem`) → 같은 technical_theme 그룹핑 → 인과관계 체인 생성
- Self-critique 단계: "이 체인이 논리적으로 타당한가?" LLM 재질문
- `CausalChain` 모델: steps, connections, confidence, evidence
- Confidence < 0.6 체인 필터링 (틀린 체인 > 없는 체인)
- Wrapup이 Chain 출력 사용 → key_insights 생성

**상태:** ⚪ Task 2 결과에 따라 결정
**설계:** `~/.gstack/projects/rutesun-invest-jarvis/user-main-design-20260429-115113.md`
**예상:** 1-2일
**의존성:** Task 2 실패 시

---

### Task 4: 뉴스 임팩트 스코어링 `P1`

**왜:**
현재 `NewsTool`은 yfinance에서 제목+요약만 가져옴.
"삼성 HBM 계약 체결" 뉴스가 나와도 → 이게 매출의 몇 %인지, 마진에 어떤 영향인지 모름.
뉴스가 **실적(Earnings), 수급(Liquidity), 심리(Sentiment)** 중 어디를 건드리는지 수치화 필요.

**뭘:**
- `news.py` 분석 시 해당 종목의 펀더멘털 지표 (P/E, 매출, 영업이익률) 컨텍스트 주입
- LLM에 "이 뉴스가 위 지표를 바꿀 수 있는가?" 질문
- 임팩트 분류: Earnings Impact / Liquidity Impact / Sentiment Only
- 임팩트 크기 추정: High / Medium / Low + 근거
- Daily Report의 각 뉴스 항목에 임팩트 배지 표시

**상태:** 🟡 아이디어
**설계:** 없음 (설계 필요)
**예상:** 2-3일
**의존성:** Task 1 (공시에서 펀더멘털 데이터 활용 가능)

---

### Task 5: Cross-Check Engine (모순 감지) `P1`

**왜:**
기술적 분석(8-컴포넌트)과 뉴스/공시의 방향성이 충돌할 때가 있음.
예: "실적 호재로 5% 상승" (뉴스 긍정) vs "RSI 80 + 거래량 -30%" (기술적 = 분산 가능성)
현재는 이 충돌을 **아무도** 알려주지 않음.

**뭘:**
- `jarvis analyze` 파이프라인에서 기술적 분석 결과 + 뉴스/공시 감성을 비교
- 방향성 충돌 시 경고 생성: "⚠️ 뉴스 긍정 vs 기술적 부정 → 확인 필요"
- Confidence Score ("확신도") 리포트에 명시
- 실행 가능한 인사이트: "거래량 확인 필요" / "단기 과열 주의" / "저점 매집 가능성"
- Daily Report에도 모순 섹션 추가 (선택)

**상태:** 🟡 아이디어
**설계:** 없음 (설계 필요)
**예상:** 3-5일
**의존성:** Task 2 또는 Task 3 완료 후

---

### Task 6: 공시 정량 시뮬레이션 `P2`

**왜:**
공시는 숫자가 핵심인데, 현재는 텍스트 요약만 함.
유상증자 공시 → "희석 비율 몇 %?" 없음.
공급계약 체결 → "전년 매출 대비 비중?" 없음.
투자 결정에 필요한 **임팩트 크기**를 정량화해야 함.

**뭘:**
- 공시 유형별 추론 템플릿 도입 (`disclosure.py`)
  - 전환사채: 잠재적 오버행 물량 % 계산
  - 유상증자: 발행가액, 희석 비율, 자금 조달 목적 분류
  - 공급계약: 전년 매출 대비 비중 계산
  - 실적 발표: 컨센서스 대비 서프라이즈 %
- 핵심 숫자(금액, 비중, 날짜) 정규화 모듈
- 리포트에 임팩트 수치 포함 ("오버행 물량 12%", "매출 비중 8%")

**상태:** 🟡 아이디어
**설계:** 없음 (설계 필요)
**예상:** 3-5일
**의존성:** Task 1 (공시 파싱 인프라)

---

### Task 7: 경쟁사 비교 `P2`

**왜:**
같은 공급망/테마 안에서 누가 수혜이고 누가 피해인지 비교하고 싶음.
예: "HBM 수요 증가 → 삼성 vs SK하이닉스 누가 더 수혜?"
예: "AI 데이터센터 → TSMC vs 삼성파운드리 마진 비교?"
현재는 종목별로 따로 분석해서 내가 머릿속에서 비교함.

**뭘:**
- 같은 체인/테마에 속한 종목들 자동 그룹핑
- 그룹 내 종목별 기술적 분석 + 펀더멘털 비교 테이블
- "상대적 강도" 스코어: 같은 테마 내에서 누가 더 강한지
- Daily Report에 "테마 내 수혜/피해 종목" 섹션 추가

**상태:** 🟡 아이디어
**설계:** 없음 (설계 필요)
**예상:** 3-5일
**의존성:** Task 3 또는 Task 4 (체인/테마 데이터 필요)

---

### ~~Task 8: Actionable Signal 고도화~~ ⛔ 제거됨 (설명 전용 종합 해설로 대체)

**히스토리:**
별도의 LLM 액션 생성 경로는 규칙이 확정한 `decision_summary`와 액션이 충돌하는
문제가 있어 제거되었다. 현재 Analyze는 규칙이 확정한 액션·타이밍을 그대로 두고,
최종 LLM은 모든 소스와 고정 decision을 받아 **설명만** 하는 종합 해설을 생성한다.
자세한 내용은 `docs/changes/unified-technical-analysis-contract.md` 참고.

---

### Task 9: Backtesting Engine `P2`

**왜:**
전략의 과거 정확도를 검증할 수 없음.
"이 전략이 맞았다"는 주장에 숫자 근거가 없음.
정확도를 측정해야 프롬프트 튜닝도 의미 있음.

**뭘:**
- 백테스팅 프레임워크 (vectorbt 또는 직접 구현)
- `BacktestConfig` 모델 (기간, 초기 자본)
- `BacktestRunner` 클래스
- 정확도 측정: precision, recall, Sharpe ratio
- CLI: `jarvis backtest AAPL --days 60`
- 결과 CSV 저장 + 요약 출력

**상태:** 🟡 아이디어 (기존 ROADMAP Phase 2)
**설계:** 없음 (설계 필요)
**예상:** 3-4시간
**의존성:** `TechnicalResult`/`technical_verdict` 및 rule-owned `decision_summary`

---

### Task 10: Multi-turn Deep Dive `P3`

**왜:**
리포트 생성 중 모호한 지점 발견 시 LLM이 **추가 검색 없이** 그냥 넘어감.
예: "블룸 에너지 계약" 언급 → 계약 규모는? 상대방은? → 모름 → 그냥 요약.
에이전트가 스스로 추가 검색해서 근거를 보충하는 루프 필요.

**뭘:**
- 리포트 생성 중 "모호한 지점" 감지 로직
- 추가 검색 도구 (SearchTool) 연동
- 근거 보충 후 리포트 재생성
- 최대 2-3회 반복 (비용 제한)

**상태:** ⚪ 장기
**설계:** 없음 (설계 필요)
**예상:** 1주
**의존성:** Task 2/3 (프롬프트/체인 안정화 후)

---

### Task 11: Backtesting Feedback Loop `P3`

**왜:**
과거 리포트의 예측과 실제 시장 움직임 비교 → LLM 프롬프트 자동 튜닝.
현재는 프롬프트를 직감으로 수정. 데이터 기반 개선 필요.

**뭘:**
- 과거 리포트 예측 vs 실제 결과 비교 시스템
- "이 프롬프트 버전의 정확도" 측정
- A/B 테스트: V3 vs V4 프롬프트 비교
- 성능 좋은 프롬프트 자동 선택

**상태:** ⚪ 장기
**설계:** 없음 (설계 필요)
**예상:** 1주+
**의존성:** Task 9 (Backtesting 인프라)

---

### Task 12: Web Dashboard `P3`

**왜:**
CLI는 충분하지만, 차트와 리포트를 한눈에 보고 싶을 때가 있음.
특히 포트폴리오 모니터링 + 백테스트 결과 시각화.

**뭘:**
- Streamlit 또는 Gradio 기반
- 종목 분석 페이지 (신호 + 차트)
- 백테스트 결과 시각화 (plotly)
- 포트폴리오 모니터링 페이지
- Docker 이미지 (선택)

**상태:** ⚪ 장기 (기존 ROADMAP Phase 3)
**설계:** 없음 (설계 필요)
**예상:** 반나절
**의존성:** Task 8, Task 9

---

### Task 13: 저항 인식 패널티 (Overhead Resistance) `P1`

**왜:**
회복 국면에서 가격이 **직전 상승추세의 주요 고점(= 슈퍼트렌드 하락전환 직전 고점)** 바로 밑까지 오면, 그건 머리 위 미돌파 저항이라 쫓아 사면 위험하다. 그런데 현재 스코어링은 이 저항을 반영 못 해 과도한 고득점을 준다.

**근거 (백테스트, 2026-08-24):**
- 실리콘투 4/24 고점 High=50,500 → 5/12 슈퍼트렌드 하락전환. 이 50,500이 회복 국면의 주요 저항.
- 오늘(8/21) 종가 47,650은 그 고점 대비 **-5.6%, 미돌파**인데 8/19 adj=80(hold), 8/21 adj=45로 저항 근접이 거의 반영 안 됨.
- 원인: `risk` 컴포넌트가 저항 레벨을 **최근 스윙 고점 5개(`tail(5)`)와 이동평균**에서만 뽑음 → 넉 달 전 4/24 고점은 안 보임 (`src/tools/technical/components/risk.py`).

**뭘:**
- "슈퍼트렌드가 직전에 하락전환하기 직전의 주요 스윙 고점"을 저항 레벨로 명시 포착 (오래된 고점도 포함)
- 미돌파 상태에서 그 저항에 근접하면 점수 감점, 종가 돌파 확정 시 오히려 가산
- risk 컴포넌트 또는 별도 컴포넌트로 구현 검토

**상태:** 🟡 근거 확보, 설계 필요
**설계:** 없음 (설계 필요)
**관련:** `docs/superpowers/specs/2026-08-24-bottom-watch-design.md` (같은 백테스트에서 파생)

---

### Task 14: bottom_watch 구조 점수 (higher-low) `P2`

**왜:**
bottom_watch 이진 플래그를 넘어, "직전 저점보다 높은 저점 + cRSI 저점 상승"이 실제로 형성되면 바닥 확신이 커지므로 강도를 점수화하고 싶다.

**보류 근거 (백테스트, 2026-08-24):**
- 같은 시점 가산 프로토타입에서 **참/가짜 바닥이 역전**됨: 엘앤에프 가짜 바닥 7/10이 70점, 진짜 바닥 7/31이 40점.
- 원인 (1) higher-low는 정의상 바닥 당일엔 존재 불가(바닥 뒤 형성), (2) 일봉 저점 스윙 감지가 데드캣 바운스를 오인식, (3) cRSI higher-low는 divergence 컴포넌트 정의에 이미 포함(중복).
- 종목 2개 중 1개가 역전 → 샘플 부족으로 공식 튜닝 시 과적합.

**뭘:**
- 로버스트한 스윙/피벗 감지 구현
- 10종목 이상 백테스트로 참/가짜 바닥 분포 확보 후 점수 공식 설계
- "확인 tier"(바닥 직후 higher-low 형성 시 강도 상향) 형태 검토

**상태:** 🔵 보류 (샘플 확보 후 설계)
**설계:** 없음 (샘플 필요)
**관련:** `docs/superpowers/specs/2026-08-24-bottom-watch-design.md`

---

## 우선순위 요약

```
✅ 완료                즉시 (이번 주)          다음 (1-2주)           나중에 (1개월+)
──────────            ─────────────          ─────────────          ─────────────
Task 8: Actionable    Task 1: 공시 원문파싱   Task 3: Chain 스테이지   Task 10: Multi-turn
                      Task 2: 프롬프트 개선   Task 4: 뉴스 임팩트      Task 11: Feedback Loop
                                             Task 5: Cross-Check     Task 12: Web Dashboard
                                             Task 6: 공시 정량화
                                             Task 7: 경쟁사 비교
                                             Task 9: Backtesting
```

## 의존성 그래프

```
Task 1 (공시 원문) ─────────→ Task 6 (공시 정량화)
      │                       
      └──→ Task 4 (뉴스 임팩트)

Task 2 (프롬프트) ──실패──→ Task 3 (Chain)
      │                       │
      └──→ Task 5 (Cross-Check)└──→ Task 7 (경쟁사 비교)

✅ Task 8 (Actionable) ──→ Task 9 (Backtesting) ──→ Task 11 (Feedback Loop)

Task 9 + Task 8 ────→ Task 12 (Dashboard)

Task 2/3 안정화 ────→ Task 10 (Multi-turn)
```

## 설계 문서

| Task | 설계 문서 | 상태 |
|------|----------|------|
| Task 1 | `user-main-design-20260423-174653.md` | ✅ 완료 |
| Task 2-3 | `user-main-design-20260429-115113.md` | ✅ 완료 |
| Task 8 | 구현 완료 (설계 불필요) | ✅ 완료 |
| Task 4-7, 9-12 | 없음 | 🔲 설계 필요 |
