"""Reduce stage용 Few-shot 예시."""

REDUCE_EXAMPLE_1 = """
**테마**: AI 데이터센터 전력 인프라

**관련 이슈들**:
- Oracle-Bloom Energy 2.8GW 연료전지 계약
- LS ELECTRIC 북미 배전반 1,700억원 수주
- 2030년 DC 전력 수요 1,350TWh 전망

**관련 뉴스**:
- Bloom Energy CEO: "AI 인프라 전력 수요 폭발적 증가"
- 한국 전력기기 3사 북미 수주 가시화

**출력**:
```json
{
  "theme": "AI 데이터센터 전력 인프라",
  "emoji": "⚡",
  "summary": "🔋 Oracle-Bloom Energy 2.8GW 연료전지 계약 체결\\n📈 LS ELECTRIC 북미 AI DC 배전반 1,700억원 수주\\n⚡ 2030년 DC 전력 수요 1,350TWh 전망 (+220%)\\n🌐 한국 전력기기 3사 북미 진출 본격화",
  "impact": "전력 인프라 병목 해소로 AI 투자 가속화. 한국 전력기기 기업들의 글로벌 수주 레벨업 기대. Bloom Energy-Oracle 파트너십은 청정 에너지 기반 AI 인프라 확산의 신호탄",
  "stocks": [
    {
      "name": "LS ELECTRIC",
      "ticker": "010120.KS",
      "catalyst": "북미 AI 데이터센터 배전반 1,700억원 공급 계약 체결"
    }
  ]
}
```

**핵심 포인트**:
- Summary에 이모지 적절히 사용 (🔋⚡📈🌐)
- Bullet point 형식으로 가독성 확보
- Impact는 시장 영향 + 투자 시사점 포함
- 관련 종목은 촉매 뉴스와 함께 명시
"""


def get_reduce_examples() -> str:
    """프롬프트용 포맷팅된 Reduce 예시 반환."""
    return REDUCE_EXAMPLE_1
