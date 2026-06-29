# Change Record: Stock Report V2 Typed Evidence + QA Warnings

**Status**: In Progress
**Date**: 2026-05-22
**PRs**: -
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

`supporting_facts` 단일 리스트에 사실/수치/논리/리스크가 섞여 있었다. LLM 출력에
`핵심 수치`, `작성자 코멘트`가 누적되면서 facts와 interpretation의 경계가 흐려졌고,
추출 품질 회귀가 잡히지 않았다. LLM 의미 판단(evidence 분류)과 코드 정규화/검증
(숫자 포맷, QA warning)을 분리하면 두 레이어가 서로를 오염시키지 않는다.

## What

1. **`EvidenceItem` 모델 도입 + LLM 출력 계약 전환**: `supporting_facts` 자유 텍스트
   대신 `evidence_items`(kind: fact/metric/risk/logic, text, value?) 타입 배열을 LLM
   출력 계약으로 삼는다. `supporting_facts`는 하위 호환용 파생 필드로만 유지. kind 분류가
   LLM 역할, 숫자 포맷 검증이 코드 역할로 명확히 분리된다.

2. **`QAWarning` + warning 정책 (`knowledge_chunks.qa_warnings`)**: 숫자/메시지타입 품질
   경고를 4종 도입했다. `unsupported_numeric`(뒷받침 숫자 없는 수치 주장),
   `missing_metric_candidate`(metric kind인데 value 없음), `long_evidence`(300자 초과),
   `admin_contradiction`(공시와 충돌 의심). Phase 1은 warning-only: 경고 발생 시 파이프라인을
   중단하지 않고 DB에 저장만 한다. 쌓인 warning 패턴을 확인 후 Phase 2에서 hard gate 도입
   여부를 결정한다.

3. **grouped-only chunk fake evidence 제거**: 그룹 집계에만 쓰이는 chunk가 빈 `supporting_facts=[]`
   대신 임의 text를 채우던 문제를 `evidence_items=[]` 명시적 빈 배열로 교체했다.
   fake evidence가 상위 합성 단계로 흘러들어가는 경로를 차단.

4. **tuning/viewer evidence 가시화**: kind 단위로 evidence를 그룹화해 뷰어에 표시.
   fact/metric/risk/logic이 어떤 비율로 뽑히는지 tuning 세션에서 육안 확인 가능.

## Before / After

```
Before (LLM 출력 계약):
  supporting_facts: list[str]
  # "삼성전자 2Q 영업이익 10.4조 (YoY +1340%)", "작성자 코멘트: 반도체 회복 가속"
  # → 사실/수치/해석이 구분 없이 섞임

After:
  evidence_items: list[EvidenceItem]
  # {kind: "metric", text: "2Q 영업이익 10.4조", value: 10.4}
  # {kind: "fact",   text: "반도체 수요 회복으로 전 부문 흑자 전환"}
  # {kind: "risk",   text: "HBM 경쟁 심화 리스크"}
```

```
Before (grouped-only chunk):
  supporting_facts: []   → 빈 배열 대신 임의 텍스트가 채워지는 경우 있었음

After:
  evidence_items: []     → 명시적 빈 배열, fake evidence 상위로 유출 안 됨
```

## Impact

tuning/viewer에서 evidence를 `fact / metric / risk / logic` kind별로 구분해서 볼 수 있다.
QA warning(`unsupported_numeric`, `missing_metric_candidate` 등)이 DB에 쌓여 품질 추이를
확인할 수 있다. Phase 1은 warning이 파이프라인을 막지 않으므로 사용자 가시 동작 변화는 없다.

## Constraints

- **Phase 1 warning-only**: `unsupported_numeric` 같은 경고가 실제로 얼마나 발생하는지
  1주일 데이터로 먼저 관찰한다. false positive 비율이 높으면 regex 기반 숫자 QA의 감지
  기준을 조정해야 한다. 확인 전에 hard gate를 걸면 파이프라인이 과도하게 차단될 수 있다.
- **regex 숫자 QA 한계**: 특수 표기(예: `$1.2B`, `₩1,200억`)에서 false positive/negative가
  발생할 수 있다. 정규화 규칙은 점진 확장으로 보완한다.

## Related

- 설계: `docs/superpowers/specs/2026-05-21-stock-report-typed-evidence-design.md`
- ADR: 없음
- FEATURES.md: 머지 후 업데이트
- 후속: warning 패턴 1주일 관찰 → Phase 2 hard gate 도입 여부 결정
