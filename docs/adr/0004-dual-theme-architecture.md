# ADR-0004: NewsItem theme을 technical/investment 이중 구조로 분리

**상태:** 수락
**날짜:** 2026-04-19

## 컨텍스트

기존 NewsItem에는 단일 `theme` 필드만 존재했다. 이 필드가 두 가지 역할을 동시에 수행하고 있었다:
1. Shuffle 스테이지에서 그룹핑 키로 사용 (안정적, 검색 가능해야 함)
2. 최종 리포트에서 사용자에게 표시 (읽기 좋고 투자 내러티브를 담아야 함)

한 필드로 두 역할을 만족시키기 어려웠다. 검색에 최적화하면 딱딱해지고, 내러티브를 담으면 클러스터링 일관성이 떨어졌다.

## 고려한 옵션

### 옵션 A: 단일 theme 유지 + 프롬프트 튜닝
- 장점: 모델 변경 없음
- 단점: 두 역할의 충돌이 근본적으로 해결 안 됨

### 옵션 B: technical_theme / investment_theme 분리
- 장점: 각 필드가 명확한 단일 역할, Shuffle은 technical_theme으로 안정적 그룹핑, 사용자에게는 investment_theme으로 표시
- 단점: 모델 변경, 기존 프롬프트/파이프라인 수정 필요

## 결정

옵션 B 채택.

- `technical_theme`: Shuffle에서 생성, 안정적 검색/그룹핑 키
- `investment_theme`: Reduce LLM이 생성, 20-40자 투자 내러티브 (방향성 명확)
- `keywords`: 검색 최적화용 키워드 리스트 (종목명, 기술용어, 트렌드)

## 결과

- NewsItem/ThemeAnalysis 모델에 `technical_theme`, `investment_theme`, `keywords` 필드 추가
- 기존 단일 `theme` 필드 제거
- Reduce 프롬프트(V2)에서 investment_theme 생성 지침 추가
- Wrapup 프롬프트(V2)에서 investment_theme 기반 인사이트 도출
- 리포트 출력에서 investment_theme을 제목으로 표시, keywords를 검색 태그로 활용
