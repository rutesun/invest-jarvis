# ADR-0003: Provider 조건부 Anthropic 프롬프트 캐싱

**상태:** 수락
**날짜:** 2026-04-18

## 컨텍스트

Daily Report 파이프라인에서 4개 스테이지가 동일한 system prompt로 다수의 LLM 호출을 수행한다 (Map: 2-4회, Shuffle: 5-15회, Reduce: 10-30회). Anthropic API는 `cache_control: {"type": "ephemeral"}`로 프롬프트 캐싱을 지원하여 반복 호출 시 입력 토큰 비용을 90% 절감할 수 있다.

문제: `config.py`에서 스테이지별 provider를 OpenAI로 변경할 수 있도록 설계했으므로, Anthropic 전용 파라미터를 하드코딩하면 provider 전환 시 에러가 발생한다.

## 고려한 옵션

### 옵션 A: 각 스테이지에서 provider 분기
- 장점: 단순
- 단점: 4개 스테이지에 동일한 if/else 분기 중복

### 옵션 B: `StageLLMConfig.build_messages()`에서 provider 자동 판단
- 장점: 한 곳에서 관리, 스테이지 코드에서 `SystemMessage`/`HumanMessage` 직접 생성 불필요
- 단점: config가 메시지 생성까지 담당 (약간의 책임 확대)

## 결정

옵션 B 채택. `StageLLMConfig.build_messages(system_prompt, user_prompt)`가 provider를 확인하고 Anthropic이면 `cache_control`을 자동 추가한다.

## 결과

- 4개 스테이지에서 `SystemMessage`/`HumanMessage` import 제거
- 각 스테이지는 `XXX_LLM.build_messages(system, user)` 한 줄로 메시지 생성
- OpenAI로 전환해도 동작 변경 없음 (`cache_control` 자동 비활성화)
- Anthropic 사용 시 2회차 호출부터 system prompt 토큰 비용 90% 절감
