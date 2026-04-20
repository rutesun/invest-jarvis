# ADR-0005: LLM ValidationError 재시도 시 에러 피드백 전달

**상태:** 수락
**날짜:** 2026-04-19

## 컨텍스트

`with_structured_output()`으로 Pydantic 모델 검증을 적용하면 LLM이 스키마에 맞지 않는 값을 반환할 때 ValidationError가 발생한다. 기존 재시도 로직(`llm_utils.py`)은 동일 프롬프트로 재시도하여 같은 에러를 반복하는 경우가 많았다.

실제 사례: IssueCategory에 없는 `"의료/바이오"`, `"광통신"` 같은 값을 LLM이 반환 → Pydantic 검증 실패 → 재시도해도 동일 실패.

## 고려한 옵션

### 옵션 A: 재시도 횟수 증가
- 장점: 단순
- 단점: 동일 프롬프트면 같은 에러 반복, 비용만 증가

### 옵션 B: ValidationError 메시지를 LLM에 피드백하여 재시도
- 장점: LLM이 어떤 제약을 위반했는지 알 수 있어 수정 가능성 높음
- 단점: 메시지 구성 복잡도 증가, 토큰 소비 약간 증가

### 옵션 C: Pydantic 모델에 lenient 모드 적용 (strict=False)
- 장점: 검증 실패 자체가 줄어듦
- 단점: 잘못된 데이터가 파이프라인 하류로 전달됨

## 결정

옵션 B 채택. ValidationError 발생 시:
1. 에러 메시지에서 위반된 필드와 제약 조건 추출
2. 필드별 요구사항과 올바른 예시를 포함한 피드백 메시지 구성
3. 기존 메시지 + 피드백을 포함하여 LLM 재호출

## 결과

- `llm_utils.py`의 `invoke_llm_with_retry`에서 ValidationError를 별도 처리
- 재시도 시 `HumanMessage`로 에러 상세 + 필드 요구사항 + 예시를 추가 전달
- `field_specs` 딕셔너리로 필드별 제약/예시를 관리 (investment_theme: 20-40자, keywords: 5-10개 등)
- 카테고리 Literal 위반 같은 반복 실패의 성공률 향상
