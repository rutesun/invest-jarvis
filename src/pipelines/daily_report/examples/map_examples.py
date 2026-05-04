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


MAP_EXAMPLE_3 = """
**입력 메시지**:
```
[msg1] LG에너지솔루션 ESS용 배터리 1Q 판매량 전분기비 15% 증가
[msg2] 삼성SDI 전고체 배터리 파일럿 라인 Q2 가동 예정
[msg3] SK온 미국 공장 가동률 70% 돌파
[msg4] 현대차 전기차 판매 목표 하향, 1Q 재고 증가
```

**출력**:
```json
[
  {
    "title": "국내 배터리 3사 생산 정상화, 전기차 수요 둔화와 대조",
    "summary": "LG에너지솔루션 ESS 판매 15% 증가, 삼성SDI 전고체 파일럿 Q2 가동, SK온 미국 가동률 70% 돌파로 공급망 회복세. 반면 현대차 전기차 판매 목표 하향 및 재고 증가로 수요 둔화 가시화. 배터리 업사이클 기대감이 완성차 실적 부진과 상충하며 투자 방향성 혼재",
    "themes": ["배터리 생산 정상화", "전기차 수요 둔화"],
    "keywords": ["LG에너지솔루션", "삼성SDI", "SK온", "현대차", "ESS", "전고체 배터리", "전기차"],
    "sentiment": "neutral",
    "source_ids": ["msg1", "msg2", "msg3", "msg4"]
  }
]
```

**핵심 포인트**:
- 4개 메시지 → 1개 이슈 (avg_sources = 4.0) - 공격적 통합 성공!
- 배터리 3사 + 완성차를 하나의 내러티브로 엮음 (공급/수요 대비)
- 서로 다른 기업이지만 동일 산업 밸류체인 → 통합 가능
"""


MAP_EXAMPLE_BAD = """
**❌ 나쁜 예시 (과도한 분절화)**:
```
**입력 메시지**:
[msg1] 팔란티어 1분기 매출 7.7억 달러, 전년비 21% 증가
[msg2] 팔란티어 미국 정부 매출 40% 증가
[msg3] 팔란티어 엔터프라이즈 AI 솔루션 채택 확대

❌ 잘못된 출력:
[
  {
    "title": "팔란티어 매출 증가",
    "summary": "1분기 매출 7.7억 달러, 전년비 21% 증가",
    "themes": ["AI 소프트웨어"],
    "keywords": ["팔란티어"],
    "sentiment": "bull",
    "source_ids": ["msg1"]
  },
  {
    "title": "팔란티어 정부 매출 호조",
    "summary": "미국 정부 매출 40% 증가",
    "themes": ["AI 소프트웨어"],
    "keywords": ["팔란티어"],
    "sentiment": "bull",
    "source_ids": ["msg2"]
  },
  {
    "title": "팔란티어 엔터프라이즈 확대",
    "summary": "엔터프라이즈 AI 솔루션 채택 확대",
    "themes": ["AI 소프트웨어"],
    "keywords": ["팔란티어"],
    "sentiment": "bull",
    "source_ids": ["msg3"]
  }
]
```
**문제점**: 3개 메시지 → 3개 이슈 (avg_sources = 1.0) - 압축 실패!


**✅ 좋은 예시 (공격적 클러스터링)**:
```
**입력 메시지**:
[msg1] 팔란티어 1분기 매출 7.7억 달러, 전년비 21% 증가
[msg2] 팔란티어 미국 정부 매출 40% 증가
[msg3] 팔란티어 엔터프라이즈 AI 솔루션 채택 확대

✅ 올바른 출력:
[
  {
    "title": "팔란티어 실적 호조, 정부·엔터프라이즈 AI 수요 동시 확대",
    "summary": "1분기 매출 7.7억 달러(전년비 21% 증가). 미국 정부 매출 40% 급증, 엔터프라이즈 AI 솔루션 채택 가속화로 양대 시장 동시 성장",
    "themes": ["엔터프라이즈 AI 채택 가속", "AI 소프트웨어 실적 개선"],
    "keywords": ["팔란티어", "정부 매출", "AI 에이전트", "엔터프라이즈"],
    "sentiment": "bull",
    "source_ids": ["msg1", "msg2", "msg3"]
  }
]
```
**핵심**: 3개 메시지 → 1개 이슈 (avg_sources = 3.0) - 성공!
"""


def get_map_examples() -> str:
    """프롬프트용 포맷팅된 Map 예시 반환."""
    return f"{MAP_EXAMPLE_1}\n\n{MAP_EXAMPLE_2}\n\n{MAP_EXAMPLE_3}\n\n{MAP_EXAMPLE_BAD}"
