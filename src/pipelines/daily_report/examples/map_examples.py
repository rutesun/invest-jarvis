"""Map stage용 Few-shot 예시."""

# 실제 2026-04-14 텔레그램 데이터 기반
MAP_EXAMPLE_1 = """
**입력 메시지**:
```
[msg1] Bloom Energy, Oracle에 연료전지 1.2GW 공급 계약
[msg2] LS ELECTRIC 북미 AI 데이터센터 배전반 1,700억원 수주
[msg3] Bloom Energy 워런트 발행으로 Oracle AI 인프라 확장 자금 조달
[msg4] 데이터센터 전력 수요 2030년 1,350TWh 전망 (+220%)
[msg5] 현대차 1분기 영업이익 3.2조 예상, 컨센서스 하회
[msg6] 기아 미국 판매 부진, SUV 재고 증가
```

**출력**:
```json
[
  {
    "title": "AI 데이터센터 전력 인프라 투자 급증",
    "summary": "Oracle-Bloom Energy 2.8GW 규모 연료전지 공급 계약 체결. LS ELECTRIC 북미 배전반 1,700억원 수주. 2030년까지 데이터센터 전력 수요 220% 증가 전망으로 인프라 투자 가속화",
    "themes": ["AI 데이터센터", "전력 인프라"],
    "keywords": ["Bloom Energy", "Oracle", "LS ELECTRIC", "연료전지", "배전반", "데이터센터"],
    "sentiment": "bull",
    "source_ids": ["msg1", "msg2", "msg3", "msg4"]
  },
  {
    "title": "현대차그룹 실적 부진 우려",
    "summary": "현대차 1분기 영업이익 컨센서스 하회 전망. 기아 미국 시장 판매 감소 및 SUV 재고 증가로 수익성 압박",
    "themes": ["자동차 실적 부진", "재고 증가"],
    "keywords": ["현대차", "기아", "SUV"],
    "sentiment": "bear",
    "source_ids": ["msg5", "msg6"]
  }
]
```

**핵심 포인트**:
- Bloom Energy 관련 3개 메시지를 하나의 이슈로 통합 (중복 방지)
- LS ELECTRIC도 같은 테마(전력 인프라)에 포함
- 현대차/기아는 별도 이슈 (다른 테마)
"""


MAP_EXAMPLE_2 = """
**입력 메시지**:
```
[msg1] 삼성전자 HBM3E 엔비디아 검증 통과 임박
[msg2] SK하이닉스 HBM3E 12단 양산 시작
[msg3] 마이크론 HBM3E 가격 20% 인상 발표
```

**출력**:
```json
[
  {
    "title": "HBM 메모리 공급 부족 심화",
    "summary": "삼성전자 엔비디아 검증 통과 임박, SK하이닉스 12단 양산 개시. 마이크론 가격 20% 인상으로 공급 부족 가시화",
    "themes": ["AI 메모리 업사이클", "HBM 공급 부족"],
    "keywords": ["삼성전자", "SK하이닉스", "마이크론", "HBM3E", "엔비디아"],
    "sentiment": "bull",
    "source_ids": ["msg1", "msg2", "msg3"]
  }
]
```

**핵심 포인트**:
- 3개 메시지가 모두 HBM 주제 → 하나의 이슈로 통합
- 테마는 "반도체" (X) → "AI 메모리 업사이클" (O) - 구체적
"""


def get_map_examples() -> str:
    """프롬프트용 포맷팅된 Map 예시 반환."""
    return f"{MAP_EXAMPLE_1}\n\n{MAP_EXAMPLE_2}"
