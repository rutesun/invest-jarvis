# ADR-0002: VIX 기반 Fear & Greed 추정을 CNN 원본 데이터로 교체

**상태:** 수락
**날짜:** 2026-04-18

## 컨텍스트

Ingest 스테이지에서 Fear & Greed Index를 VIX 값 하나로 3단계(30/50/70) 이산 분류하고 있었다. VIX 14.9→15.0에서 70→50으로 급변하고, 실제 CNN Fear & Greed Index가 사용하는 7개 지표 중 1개만 반영하여 정확도가 낮았다.

## 고려한 옵션

### 옵션 A: VIX 기반 선형 보간 함수
- 장점: 외부 의존성 없음, 급변 문제 해결
- 단점: 여전히 VIX 단독 지표, 실제 Fear & Greed와 괴리

### 옵션 B: 7개 지표 직접 구현
- 장점: CNN과 동일한 정확도
- 단점: Put/Call Ratio, NYSE Breadth 등 무료로 구하기 어려운 데이터 필요, 가중치 비공개

### 옵션 C: CNN `fear-and-greed` 패키지 사용
- 장점: 원본 데이터 그대로, 구현 비용 최소 (`fear_and_greed.get()` 한 줄), 1분 내장 캐시
- 단점: 외부 의존성 추가, CNN 사이트 장애 시 실패

## 결정

옵션 C 채택. `fear-and-greed` PyPI 패키지로 CNN 원본 값을 가져오고, 실패 시 50(Neutral)으로 폴백.

## 결과

- `fear-and-greed` 의존성 추가
- VIX 기반 if/elif/else 계산 로직 삭제
- CNN API 실패 시 3회 리트라이 (exponential backoff) 후 50으로 폴백
- 매크로 데이터 전체에 동일한 리트라이 패턴 적용
