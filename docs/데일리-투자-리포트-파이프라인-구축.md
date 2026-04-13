# 데일리 투자 리포트 파이프라인 구축

**Date**: April 12, 2026 at 01:59 AM
**Turns**: 1
**Source**: [Gemini Chat](https://gemini.google.com/app/0118b67fa75a092c?utm_source=app_launcher&utm_medium=owned&utm_campaign=base_all)

---

## Turn 1

### 🤖 Assistant

텔레그램의 깊이 있는 정보와 시장의 실시간성을 결합한 **최종 데일리 리포트 파이프라인**과 그 과정에서의 **LLM 역할 및 필수 툴**을 정리하여 제안합니다.

---

### 1. 최종 데일리 리포트 플로우 (Pipeline)
전체 과정은 데이터의 지연을 방지하기 위해 **병렬 수집**과 **계층적 분석**으로 구성됩니다.

#### **1단계: 원시 데이터 병렬 수집 (Data Ingestion)**

- **시장의 온도 (Pulse)**: `macro.py`를 통한 매크로 지표(VIX, 금리, Fear & Greed 등) 및 `news.py`를 통한 실시간 주요 지수 뉴스 수집.
- **돈의 흐름 (Flow)**: `naver.py` 및 `kis.py`를 통해 당일 상위 테마, 외인/기관 순매수(Smart Money) 특징주 추출.
- **현장의 목소리 (Intelligence)**: 전날 및 당일 텔레그램 메시지 CSV 로드.

#### **2단계: LLM 분석 (Map-Shuffle-Reduce)**

- **Map**: 텔레그램 메시지를 청크별로 분석하여 섹터, 토픽을 추출하고 시장 영향(Bull/Bear/Neutral) 태깅.
- **Shuffle & Filter**: 추출된 엔티티(회사명/티커)를 정규화하고, 빈도수와 수급 데이터를 대조하여 핵심 이슈 선별.
- **Reduce**: 파편화된 정보를 통합하여 **'시장 내러티브(Market Narrative)'**와 테마 간 연결고리 생성.

#### **3단계: 촉매제 분석 (Catalyst Synthesis)**

- **수급+뉴스 매칭**: 수급이 집중된 종목이나 테마 주도주에 대해 `NewsTool`을 가동하여 급등의 이유(공시, 보도자료)를 즉시 매핑.

#### **4단계: 리포트 생성 및 포트폴리오 연계**

- 시각화된 리포트 출력 및 사용자 보유 종목에 대한 직접적 영향도 평가.

---

### 2. LLM의 단계별 역할
LLM은 단순 요약을 넘어 데이터 사이의 **문맥(Context)**을 만드는 역할을 수행합니다.

| 단계 | LLM의 핵심 역할 | 상세 내용 |
| --- | --- | --- |
| 분류 (Classification) | 텔레그램 메시지 태깅 | 메시지별 섹터 분류 및 시장 영향력(Bull/Bear/Neutral) 판단 |
| 정규화 (Normalization) | 엔티티 통일 및 필터링 | '엔비디아', 'NVDA' 등을 하나의 객체로 통합하고 노이즈 제거 |
| 추론 (Inference) | 테마 간 상관관계 감지 | 매크로 변화가 특정 섹터에 미치는 연쇄 효과 분석 |
| 합성 (Synthesis) | 시장 내러티브 생성 | 파편화된 뉴스, 지표, 메시지를 엮어 하나의 시장 스토리 작성 |
| 평가 (Evaluation) | 액션 레벨 부여 | 이슈의 중요도에 따라 '관심/모니터/즉시대응' 레벨 결정 |

---

### 3. LLM에게 제공해야 할 필수 툴 (Toolbox)
LLM이 정확한 분석을 수행하기 위해 다음 툴들을 API 형태로 제공해야 합니다.

1. **TickerResolver (엔티티 해결)**: 텔레그램에서 언급된 회사명을 정확한 티커(.KS, .KQ 등)로 변환하기 위해 필요합니다.
2. **NewsTool (촉매제 검색)**: 수급이 포착된 종목의 급등 이유를 DDGS나 yfinance를 통해 실시간으로 검색할 때 사용합니다.
3. **MacroTool (문맥 파악)**: 현재 시장이 리스크 온(Risk-on)인지 오프(off)인지 판단할 기초 데이터를 제공합니다.
4. **SectorMetrics (우선순위 가이드)**: 섹터별로 중요하게 봐야 할 핵심 지표(예: IT는 PSR, 금융은 PBR)를 LLM에게 컨텍스트로 제공합니다.
5. **FundamentalTool**: 특징주의 재무 건전성과 밸류에이션을 즉시 체크하여 수급의 연속성을 판단합니다.

---

### 4. 결론 및 제안
이 플로우를 통해 **텔레그램의 깊이**와 **뉴스의 속도**를 동시에 확보할 수 있습니다. 특히 **2단계의 정규화(Shuffle)** 과정과 **3단계의 뉴스 툴 연동**을 강화하면, 정보가 흩어지거나 뉴스가 늦어지는 고민을 효과적으로 해결할 수 있을 것입니다. 이 설계는 `invest-jarvis`의 비전인 '단순 나열이 아닌 인사이트 중심의 리포트'를 구현하는 핵심 기반이 됩니다.

---

*Exported from [Voyager](https://github.com/Nagi-ovo/gemini-voyager)*  
*Generated on April 12, 2026 at 01:59 AM*