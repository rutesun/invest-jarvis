# Change Record: jarvis brief — 일일 포트 액션 종합

**Status**: Draft
**Date**: 2026-07-14
**PRs**: #{PR 번호}
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

기존 `portfolio` 명령은 KIS 실시간 잔고를 전제로 하는데 사용자 계좌에 잔고가 없어 시작점부터 사용 불가였고, `report ticker`는 보유(평단·수량) 개념과 매수/매도 액션 판정이 없는 관찰 리포트였다. "정보는 많은데 내 보유·관심 종목 기준으로 오늘 뭘 할지로 좁혀지지 않는다"는 페인을 풀기 위해, 로컬 YAML을 SSoT로 삼아 오늘의 액션·우선순위·근거를 한 번에 내려주는 신규 CLI를 추가한다.

## What

1. **`jarvis brief` CLI + `BriefPipeline` 신규**: `playbook.yaml`의 holdings+watchlist 전 종목을 풀 평가해 ①Top-N 우선순위 큐 ②종목별 액션 신호 ③진입 임박 후보를 마크다운으로 출력(`reports/YYYY-MM/brief_YYYY-MM-DD.md`). 기존 파이프라인을 건드리지 않도록 부품(TechnicalAnalysisTool·PlaybookEngine·MacroTool·NewsTool·DisclosureTool·FlowTool)을 조립하는 신규 파이프라인으로 구성.
2. **"사실은 코드가, 해석은 LLM이" 하이브리드**: 액션·순위·근거는 규칙이 결정적으로 확정하고, LLM은 배치 1콜로 종목별 슬롯 문장화만 담당. LLM 실패 시 렌더러가 규칙 원문으로 fallback해 브리핑은 항상 완성된다.
3. **보유/워치 판정은 `PlaybookEngine.evaluate()` 단일 진입점**: 보유는 exit_verdict(청산/축소/보유), 워치는 gate(적격/임박/거부). RS·매집·스냅샷 조립이 엔진 내부에 있어 `evaluate_exit` 직접 호출을 피했다(설계 리뷰 반영).
4. **버킷 랭킹**: 버킷 순서를 절대 우선으로 두고 가산점(스탑 근접 +30, 급변 +20)은 동버킷 내 정렬에만 사용 — "축소+스탑근접"이 "청산"을 역전하는 왜곡을 방지. 순수 함수(`src/tools/brief/scoring.py`)로 분리해 I/O 없이 테스트.
5. **진입 임박 정의**: gate 미통과지만 필수 게이트 4개(A·B·C·E) 중 정확히 3개 충족을 임박으로 판정(checklist 기반). Stage2 개수만 보면 시장 하락·RS 약세를 무시하게 되는 문제를 회피(설계 리뷰 반영).
6. **`playbook.yaml` watchlist 섹션 + 로더 확장**: `WatchEntry` 추가, holdings 우선 중복 제거, 스키마 오류를 항목 인덱스와 함께 즉시 예외로 표면화.
7. **선행 버그픽스 — exit_rules SMA 컬럼 계약 불일치**: `exit_rules`는 `SMA20`을 찾는데 `IndicatorCalculator`는 `SMA_20`을 생성해, 실경로(`analyze` 포함)에서 SMA 매도신호·trailing_stop이 침묵 누락되고 있었다. `_get_ma`가 양쪽 컬럼명을 조회하도록 수정하고 실경로 회귀 테스트 추가.
8. **`PortfolioPipeline` 제거**: KIS 잔고 전제가 소멸해 brief가 역할을 대체. 파이프라인·`PortfolioTool`·`jarvis portfolio` 명령·관련 테스트 삭제. provider 레이어(`KISProvider.get_balance()`, `kis_models`)는 재활용 여지가 있어 보존.

## Before / After

```
Before: jarvis portfolio  → KIS 실시간 잔고 조회 → 종목별 현황 나열(수량·현재가·손익·기술점수)
        (계좌 잔고 없으면 사용 불가, 액션·우선순위 없음)
After:  jarvis brief       → playbook.yaml(보유+워치) 전 종목 평가
        → ⚡오늘의 액션 Top-3 + 종목별 [청산/축소/보유/적격/임박/거부] + 근거 슬롯
        (기술·수급·뉴스·공시 근거, 스탑 근접·급변 마커, reports/에 .md 저장)
```

```
Before(exit_rules): _get_ma(df, "SMA50")  # indicators는 "SMA_50" 생성 → 항상 None → 신호 누락
After(exit_rules):  _get_ma가 "SMA50"·"SMA_50" 양쪽 조회 → 실경로에서 SMA 신호 정상 발화
```

## Impact

- **신규 명령**: `jarvis brief [--provider openai|anthropic] [--no-llm]`. `--no-llm`은 LLM 키 없이 규칙 원문만 출력.
- **제거된 명령**: `jarvis portfolio` (대체: `jarvis brief`).
- **설정**: `playbook.yaml`에 `watchlist:` 섹션 추가 가능(티커만 필수, `note` 선택). holdings 형식은 기존과 동일.
- **부수 효과(버그픽스)**: 기존 `analyze`의 보유 종목 매도 판정에서 SMA_SHORT/SMA_LONG 신호·trailing_stop이 이제 정상 동작.
- **출력물**: `reports/YYYY-MM/brief_YYYY-MM-DD.md` 신규 생성.

## Constraints

- 포트 전체 리스크/노출 뷰(섹터 집중도·현금비중)는 이번 범위 제외.
- 신규 발굴 엔진은 3차 로드맵으로 연기 — 이번엔 워치리스트 내 "진입 임박 후보" 표면화까지만.
- Notion 업로드·스케줄 자동 실행·텔레그램 푸시 제외(추후 옵션).
- v1은 펀더멘털·구조 zone 미포함(`PlaybookEngine.evaluate`에 `fundamental=None`, `zone_set=None`) — 사이징은 ATR/-8% 기반, 섹터는 graceful None.
- KIS 실시간 잔고는 SSoT로 쓰지 않음(계좌 잔고 부재). `get_balance()` provider 메서드는 보존.
- 의사결정 피드백 루프·백테스팅은 2차 로드맵.

## Related

- 설계: [docs/superpowers/specs/2026-07-14-jarvis-brief-design.md](../superpowers/specs/2026-07-14-jarvis-brief-design.md), [docs/superpowers/plans/2026-07-14-jarvis-brief.md](../superpowers/plans/2026-07-14-jarvis-brief.md)
- ADR: 없음 (설계 문서 D9·D10에 리뷰 반영 기록)
- FEATURES.md: `brief` 섹션 추가, `portfolio` 섹션 제거
- worklog: [docs/worklog/jarvis-brief.md](../worklog/jarvis-brief.md)
- 후속: 실계정 스모크 테스트 · 2차 의사결정 피드백 루프 · 3차 발굴 엔진
