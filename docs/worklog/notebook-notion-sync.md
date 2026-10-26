# Worklog — notebook-notion-sync

- **Branch**: feature/notebook-notion-sync
- **Started**: 2026-10-14
- **Status**: PR #64 / final-local-verification-passed
- **Links**: [계획](../superpowers/plans/2026-10-14-notebook-notion-sync.md)

## (2026-10-14 14:39) [Decision] 로컬 구현 범위 갱신
- 맥락: 사용자가 기존 조사 전용 인계를 로컬 구현·검증 지시로 갱신했습니다.
- 후보: 기존 승인 질문 반복 / 설계의 추천 기본값으로 로컬 구현
- 선택: 기존 Key와 최소 schema 확장, create-verify-swap을 구현하되 실제 remote 쓰기는 하지 않습니다.
- 기각: 승인 질문 반복(명시 지시와 충돌), 자동 legacy 재렌더링(별도 검토 필요)
- ADR 후보? yes

## (2026-10-14 14:40) [Friction] uv 기본 cache 쓰기 제한
- 막힌 점: 기본 cache 경로 접근이 sandbox에서 거부되었습니다.
- 임시 대응: `--cache-dir /tmp/notebook-notion-uv-cache`로 writable cache를 사용합니다.
- 개선 아이디어: 이 worktree의 검증 명령에 같은 cache 경로를 명시합니다.

## (2026-10-14 14:45) [Bug] 목록 빈 줄과 원문 분할 경계
- 증상: 여러 빈 줄 뒤의 nested list에서 빈 목록의 min() 호출이 실패했습니다. 긴 rich_text는 문자 제한만 지키면 payload 제한을 넘을 수 있었습니다.
- 근원(root cause): child가 없는 list와 UTF-16/JSON 크기 제한을 각각 처리하지 않았습니다.
- 수정: 재현 테스트 후 빈 child 처리를 고쳤습니다. rich_text 2,000 UTF-16 units·100 items·340KB JSON 기준으로 분할하고 큰 table row는 literal로 보존합니다.
- 재발 방지 / 배운 것: 원본 113개 모두 raw Markdown exact restoration과 속성/텍스트 제한 검증을 통과했습니다.

## (2026-10-14 14:46) [Bug] Typer single-command 축약
- 증상: standalone notebook_app 테스트에서 `sync`가 extra argument로 거부됐습니다.
- 근원(root cause): 단일 command만 있는 Typer 앱은 command 이름을 축약합니다.
- 수정: 명령 그룹 callback을 추가해 실제 CLI와 테스트의 명령 구조를 일치시켰습니다.
- 재발 방지 / 배운 것: offline 및 원본 내부 artifact 차단과 잘못된 apply 조합 테스트를 통과했습니다.

## (2026-10-14 14:50) [Bug] 독립 리뷰의 안전 경계 보강
- 증상: target 교체/최초 생성 뒤 기존 참조 page가 이전 URL/literal을 유지했고, 다른 journal의 동시 apply가 중복 page를 만들 수 있었습니다. heading/caption 응답 기본 필드로 read-back이 실패했으며 candidate 제목 편집이 resume에서 덮일 수 있었습니다.
- 근원(root cause): page ID 변경의 dependency, target 단위 lock, API 정규화, mutation 직전 재검증이 부족했습니다.
- 수정: transitive RELINK 후보·선택 누락 blocker, Database 단위 lock·promotion 직전 baseline 재조회, heading/caption 정규화, candidate property/body 사전 검증을 추가했습니다. 모든 지적은 재현 테스트 RED → 수정 GREEN으로 확인했습니다.
- 재발 방지 / 배운 것: 205개 callout child·151개 table row·순환 링크·단계별 응답 유실 recovery·신규 target dependency를 fake API로 검증했습니다. 독립 재리뷰에 추가 Critical/Important 지적이 없었습니다.

## (2026-10-14 14:52) [Decision] 암묵적 schema option 변경도 별도 검토
- 맥락: Notion은 미등록 multi-select name을 page 생성 중 schema에 추가합니다.
- 후보: page create로 자동 추가 / schema proposal에 명시
- 선택: 종목·테마 신규 option도 proposal과 blocker에 포함했습니다. 현재 제안은 property 3개, 종목 option 4개, 테마 option 152개 추가입니다. 기존 옵션은 보존합니다.
- 기각: 자동 추가(별도 schema 승인 경계와 충돌)
- ADR 후보? yes

## (2026-10-14 14:57) [Friction] 전체 suite의 기존 환경 실패
- 막힌 점: 기본 `uv run pytest` 최종 결과 1480 passed / 18 failed / 15 deselected / 2 warnings (83.54s).
- 근거: HEAD `fdab31c`를 `/tmp/notebook-notion-baseline`에 export해 같은 uv 환경에서 아래 첫 11개 실패를 재현했습니다(11 failed / 3 passed). 원본 cache는 sandbox 밖이라 쓰기가 거부됐으며 chart는 기존 autouse subprocess mock과 font 탐색이 충돌합니다. 나머지 7개는 Yahoo 외부 API DNS 실패입니다.
- 임시 대응: 관련 scope 68 passed, Ruff check/format PASS. 이번 변경과 관계없는 금융 기능·cache·chart 테스트는 수정하지 않았습니다.
- 개선 아이디어: 후속 작업에서 테스트의 cache 경로를 임시 디렉터리로 주입하고 외부 API 테스트 marker와 font subprocess 경계를 정리합니다.

실패 이름:

- `tests/pipelines/test_brief.py::test_run_all_targets_included_and_ranked`
- `tests/pipelines/test_brief.py::test_run_isolates_per_ticker_failure`
- `tests/pipelines/test_brief.py::test_run_macro_failure_does_not_block`
- `tests/pipelines/test_brief.py::test_llm_failure_falls_back_to_rule_text`
- `tests/pipelines/test_brief.py::test_stale_close_warning_propagates_to_brief_item_and_render`
- `tests/pipelines/test_brief.py::test_swing_w150_line_is_reference_only`
- `tests/pipelines/test_technical_contract_parity.py::test_technical_contract_is_identical_across_check_analyze_and_brief`
- `tests/tools/technical/test_charting.py::test_render_technical_chart_basic`
- `tests/tools/technical/test_charting.py::test_render_technical_chart_with_patterns`
- `tests/tools/technical/test_charting.py::test_render_technical_chart_with_levels`
- `tests/tools/technical/test_charting.py::test_render_technical_chart_empty_df`
- `tests/tools/test_macro.py::test_macro_tool_execute`
- `tests/tools/test_macro.py::test_macro_tool_yield_spread`
- `tests/tools/test_macro.py::test_macro_tool_fear_greed_label`
- `tests/tools/test_news.py::test_news_tool_execute`
- `tests/tools/test_news.py::test_news_tool_invalid_ticker`
- `tests/tools/test_news.py::test_news_tool_limit`
- `tests/tools/test_news.py::test_news_article_fields`

## (2026-10-14 14:58) [Decision] 외부 적용 검토 산출물 고정
- 맥락: 실제 쓰기 전 필요한 구현·검증과 대상 목록을 검토 가능하게 정리해야 합니다.
- 후보: 과거 수치 재사용 / 현재 source와 remote 재조회
- 선택: 로컬 113개, remote 83 legacy, 신규 30개(8월 3/9월 26/10월 1), orphan·duplicate·unmanaged 0. schema blocker 1과 unresolved wikilink warning 62개를 manifest에 저장했습니다.
- 기각: 과거 신규 29개 수치(원본이 변경됨)
- ADR 후보? no

## (2026-10-22 10:29) [Decision] 기존 종목 속성으로 문서를 함께 조회
- 맥락: 사용자가 삼성전자 관련 여러 문서를 같은 종목으로 묶는 로컬 수정과 미리보기 검증을 승인했습니다.
- 후보: 새 종목 DB/relation / 기존 multi-select의 값 통일 / 본문 언급 자동 추정
- 선택: 기존 `종목` multi-select에 canonical 이름을 채우고 `stock_groups` 미리보기를 제공합니다. 신규 속성은 필요하지 않습니다.
- 기각: 새 DB(이번 요구에 과함), 본문 자동 추정(단순 비교·인용도 종목으로 지정할 위험)
- ADR 후보? no

## (2026-10-22 10:29) [Bug] 국내 이름과 코드 분류 및 ETF 이름 보존
- 증상: 삼성전자 이름이 테마로 빠지고 005930과 분리되며 두 ETF의 거래 제목이 KODEX/SOL로 잘렸습니다.
- 근원(root cause): 미국 ticker/6자리 숫자만 인식하고 매매 제목 첫 단어만 사용했습니다.
- 수정: 국내 회사명 45개, 확인된 코드 8개, 하이닉스/LGES 별칭과 두 ETF의 정확한 이름을 정적 등록했습니다. 다종목·명시 미등록 종목·theme·fence·Key/body 보존을 검증했습니다.
- 재발 방지 / 배운 것: 분류 회귀 5 FAIL→PASS, 미리보기 2 FAIL→PASS. 관련 75 passed, scoped Ruff check/format PASS. 독립 리뷰에서 중요 신규 오류 없음.
- 범위: 전체 시장 종목 사전이 아닙니다. 미등록 6자리 숫자의 종목 분류와 아마존/AMZN의 분리는 기존 호환으로 유지합니다. 미등록 일반 tag는 theme입니다.

## (2026-10-22 10:29) [Decision] 최신 읽기 전용 검토 자료
- 맥락: 과거 수치와 manifest는 이번 원본·분류 변경을 반영하지 못합니다.
- 후보: 과거 manifest 재사용 / source와 remote 재조회
- 선택: source 117개(trades 11/thoughts 3/research 103), active remote 83 legacy, 신규 34개, duplicate/orphan/unmanaged 0. schema는 여전히 8속성입니다.
- 기각: 과거 30개 및 이전 option 수치 재사용(stale)
- ADR 후보? no

`data/notebook-notion/*-2026-10-22.json`에 snapshot·offline·review·trial·schema-proposal·verification을 저장했습니다. schema 제안은 Source Path/rich_text, Content Hash/rich_text, PDF 원문/url과 종목 option 47개·테마 option 166개 추가이며 기존 property/option은 보존합니다. SCHEMA_CHANGE_REQUIRED 1개, unresolved wikilink warning 66개, standalone 등 제외 문서 5개입니다. 삼성전자 분류 14개(다종목 9), SK하이닉스 11개. 삼성전자 본문/제목 언급만 있는 16개 Key는 verification의 `samsung_mention_without_tag_keys`에 검토용으로 보관했습니다. 원본 22개 파일 읽기 전후 hash 동일, 전체 117개 raw Markdown exact restoration 확인, 기존 .serena SHA-256도 동일합니다. 실제 Notion 쓰기/PDF/commit/push/PR은 0회입니다. 원본 단순 언급 후보와 legacy 분류는 이번에 remote에 반영하지 않았습니다.

## (2026-10-22 10:29) [Friction] 전체 suite와 네트워크 검증 경계
- 막힌 점: 전체 `MPLCONFIGDIR=/tmp/notebook-notion-mpl uv run --cache-dir /tmp/notebook-notion-uv-cache pytest -q`는 1487 passed / 18 failed / 15 deselected / 2 warnings (85.18s)입니다.
- 근거: 실패 이름 18개는 위 10-14 목록과 동일합니다. cache 경로 권한·chart subprocess/font 충돌과 외부 금융 API 연결 실패가 재현됐습니다. 이번 suite를 전체 PASS로 보고하지 않습니다. 로그 `/tmp/notebook-notion-full-2026-10-22.log`.
- 임시 대응: 무관한 기능은 수정하지 않았습니다. Notion snapshot은 sandbox 네트워크 실패 후 승인된 네트워크 접근으로 GET/schema 및 read-only query만 실행해 성공했습니다. 모든 remote 83개가 legacy라 block 비교 대상 UNCHANGED는 없습니다. 최신 snapshot으로 remote-aware plan을 생성했습니다.
- 개선 아이디어: 금융 API live 테스트와 provider-free 테스트를 분리하고 cache/font 테스트의 환경 의존을 줄이는 후속 작업이 필요합니다.


## (2026-10-22 11:12) [Pivot] 수동 종목표를 검색 API 근거로 교체
- 이전 접근: 국내 회사명45/코드8의 정적 alias를 등록해 분류했습니다.
- 전환 이유: 사용자가 검색 API로 찾아야 한다고 정정했습니다. 수동 대응표는 범위 누락과 유지보수 문제가 있어 폐기했습니다.
- 새 접근: raw metadata parser → Naver 종목 검색 → 국가/시장/code identity → 국내 API명·미국 ticker 표시. 국내 partial은 basic API의 종목 종류를 검증합니다. 기존 LLM resolver의 무조회 숫자→KOSPI 가정은 재사용하지 않았습니다.

## (2026-10-22 11:12) [Decision] 검색 근거와 미확정 분류
- 맥락: API 결과를 재현하고 테마/ticker 충돌을 임의 확정하지 않아야 합니다.
- 후보: 첫 검색 결과 사용 / 검증 근거와 미확정 분리 / AI 추론
- 선택: cache v2·30일·증분 저장, exact/token/partial 근거와 API후보 보존. 짧은 영문태그 1~3글자 ticker 충돌 및 partial ETF는 theme 유지+검토. 명시 종목 미해결·조회누락·동일표시명 identity충돌은 blocker. 신규 apply는 frozen 근거를 재현하며 만료 차단; resume만 frozen 근거의 TTL을 무시해 장기 부분실패 복구를 허용합니다.
- 기각: 첫결과/임의추론(테마를 종목으로 오분류 가능), 정적 회사목록(사용자 정정)
- ADR 후보? no

## (2026-10-22 11:12) [Bug] API 리뷰 경계 보강
- 증상: 소문자 hbm/ai가 충돌 검토를 우회하고, 반도체가 partial ETF로 승격되며, 30일 지난 부분실패 journal이 복구 불가했습니다. malformed cache는 traceback을 내고 구형cache는 partial근거 검증을 우회했습니다.
- 근원(root cause): case-sensitive guard, 종목종류 미검증, 신규적용과 resume의 동일 TTL, 중첩형식/버전 검증 부족.
- 수정: case-insensitive 충돌, partial equity API검증, frozen resume, cache v2 및 필수 match_kind/kind·중첩 자료형 검증을 추가했습니다. 모두 재현 RED→GREEN 후 독립 리뷰의 P2 해결 확인을 받았습니다.
- 재발 방지 / 배운 것: 관련 133 passed, 공개 raw검색/basic→최종종목 golden tests, 117항목 raw Markdown 복원 일치. 원본·기존dirty·Notion은 변경하지 않았습니다.

## (2026-10-22 11:12) [Friction] 전체 metadata 검색 외부 전송 차단
- 막힌 점: 원본에서 추출한 종목·태그 검색어542개를 Naver로 보내는 전체 dry-run이 자동 승인 검토에서 거부됐습니다. 해당 일괄 검색은 실행하지 않았으며 우회하지 않았습니다.
- 자동 검토 사유: “사용자는 검색 API 사용 취지는 승인했지만 전체 개인 노트 메타데이터를 해당 목적지에 보내는 범위까지 명시적으로 승인하지 않았습니다.”
- 임시 대응: 공개 instrument 샘플 실제 응답11개만 로컬 근거로 사용했습니다. source117개 중 unique queries542, 기존 공개샘플 cache로 확인하지 못한 query538개. 외부 전송 없이 partial-v2 manifest와 offline CLI를 검증했습니다. block: SCHEMA_CHANGE_REQUIRED / STOCK_SEARCH_INCOMPLETE / UNRESOLVED_EXPLICIT_STOCK. 완전한 API분류·schema option수·적용 manifest로 보고하지 않습니다.
- 개선 아이디어: 사용자에게 전송 대상542개검색어(본문·전체제목·출처URL 제외)와 Naver 목적지를 명시해 승인받은 뒤 full API dry-run을 재개합니다. 실제 Notion/schema/PDF/commit 승인은 여전히 포함하지 않습니다.

최신 private 검토물: public-samples-cache-api-v2-2026-10-22.json, review-api-partial-v2-2026-10-22.json, offline-api-partial-v2-2026-10-22.json. 과거 정적 review/trial/schema proposal 및 실험 v1 cache는 보존하되 적용하지 않습니다. schema 추가3속성 자체는 동일하지만 option 전체는 API분류 완료 후 다시 산출해야 합니다.


최종 API-v2 검증: 관련133 passed, scoped Ruff check/format PASS. 전체 suite1545 passed/18 failed/15 deselected/2 warnings(82.82s), 위10-14 목록과 동일한18개 실패입니다. 로그 `/tmp/notebook-notion-api-v2-full-2026-10-22.log`. offline CLI는 미조회 근거를 표시하고 의도대로 exit2, 실제 쓰기0회였습니다. private artifact mode0600/checksum, 원본22개파일hash 및 .serena초기hash 동일을 최종 확인했습니다.


## (2026-10-22 11:57) [Decision] 검색어 전송 승인 후 전체 조회
- 맥락: 사용자가 542개 종목·테마 검색어를 Naver로 전송하는 질문에 “ㅇㅇ”로 명시 승인했습니다.
- 후보: 기존 승인 대기 유지 / 승인 범위의 읽기 전용 조회 재개
- 선택: 승인 시점542개 목록을 고정해 조회하고 remote-aware plan을 생성했습니다. 본문·전체제목·출처URL은 전송하지 않으며 실제 Notion쓰기 금지는 유지합니다.
- 기각: 동일 승인 질문 반복(이미 승인), schema/page/PDF 적용(범위 밖)
- ADR 후보? no

## (2026-10-22 11:57) [Bug] nullable 국가 후보로 정상 검색 전체 중단
- 증상: 500개 성공 뒤 파마리서치 검색의 정상 KOSDAQ/KOR 후보와 함께 KONEX/nationCode:null 후보가 반환돼 전체 검색이 중단됐습니다.
- 근원(root cause): 모든 후보의 nationCode가 항상 문자열이라고 가정했습니다.
- 수정: 명시적 null은 UNKNOWN 후보로 보존하며 국가를 시장에서 추론하지 않습니다. 국가 미확인 후보만 있으면 ambiguous, 정상 exact 후보는 해결합니다. 누락/빈문자/잘못된 타입 차단은 유지합니다. 실제 공개 응답 fixture의 RED 2건을 확인한 뒤 수정했고 관련39 provider tests가 통과했습니다.
- 재발 방지 / 배운 것: 증분 cache로 기존500개를 재조회하지 않고 나머지42개를 완료했습니다. 전체 관련141 tests PASS, scoped Ruff/check-format PASS. 전체 suite1553 passed/18 failed/15 deselected/2 warnings(83.60s), 실패 이름18개는 위10-14 목록과 동일합니다. 로그 `/tmp/notebook-notion-live-full-2026-10-22.log`.

## (2026-10-22 11:57) [Friction] 조회 중 원본의 새 항목 추가 감지
- 막힌 점: 시작 시 원본22개파일 hash는 이전 baseline과 같았지만 진행 중 research 파일에 새 항목1개/검색어5개가 추가돼 현재118항목이 됐습니다. 이 작업에서는 원본에 쓰지 않았습니다.
- 임시 대응: 이전 partial manifest의 Key와 query로 승인 당시117항목/542개 검색어를 고정했습니다. 전체소스가 바뀐 뒤 첫 형식조사에서 새 일반태그 AI광고의 빈결과를 1회 확인했으나 이후 승인목록을 고정했고 신규항목의 분류는 이번 계획에서 제외했습니다. manifest에 SOURCE_SCOPE_CHANGED를 추가해 실수로 적용하지 못하게 했습니다. 현재 파일 hash는 `source-current-after-external-update.json`에 별도 보존하고 이전 baseline은 덮어쓰지 않았습니다.
- 개선 아이디어: 새 항목을 포함한 다음 검토에서는 최신 원본 범위를 다시 고정하고 manifest를 재생성합니다. 현재 review를 적용하거나 기존원본 변경을 되돌리지 않습니다.

최종 실제조회:542개(resolved168/not_found324/ambiguous50), 미조회 승인검색어0, 미해결 명시종목0. 삼성전자14개·SK하이닉스11개, 종목그룹98개. 검토query는 ambiguous50 / ticker-theme충돌30 / 부분상품명14입니다(항목별 issue197건). remote83 legacy/신규34, source없는orphan·duplicate·unmanaged0. schema는8속성 그대로이며 제안은 Source Path/rich_text, Content Hash/rich_text, PDF 원문/url과 종목option84개·테마option143개 추가입니다. 실제 Notion쓰기0회, source원본쓰기/commit/push/PR/PDF없음. .serena 초기hash동일, privateartifact0600/checksum확인. 최신파일은 review-api-complete.json, schema-proposal-api-complete.json, trial-api-complete.json, verification-api-complete.json입니다.

## (2026-10-22 17:22) [Decision] 실제 Notion 업데이트 승인 및 최신 범위 갱신
- 맥락: 사용자가 “준비만한거야? 일단 업데이트해봐 노션에서 확인하게”라고 실제 반영을 지시했습니다. 이번 지시는 이전 schema/page 쓰기 금지를 이번 반영 범위에서 갱신합니다.
- 후보: 시험 1개만 반영 / 시험 검증 후 신규 전체 반영 / legacy 동시 교체.
- 선택: 최신118항목을 재조회해 신규35개를 대상으로 삼성전자 기록1개 시험 검증 후 나머지를 반영합니다. schema3속성과 필요한 선택값만 추가합니다.
- 기각: legacy83개 동시 교체(본문·분류 migration 검토가 별도 필요). source-missing 자동archive/PDF업로드/원본수정/commit·push·PR은 진행하지 않습니다.
- 검증: 최신 dry-run은 legacy83/create35, schema blocker1, 명시종목 미확정0입니다. 관련141 tests가 새 실행에서 통과했습니다.
- 자료: data/notebook-notion/review-live-before.json 및 schema-live-patch.json. 개인 자료는 Git 제외·0600으로 보존합니다.
- ADR 후보? no

## (2026-10-22 17:27) [Friction] Notion schema 선택값 배열100개 제한
- 막힌 점: schema proposal 전체 전송이 HTTP400 validation_error로 거부됐습니다. 종목110개 options 배열은100개 제한을 초과했고, 기존 테마343개도 직접 전체전송이 불가능합니다. 진단 요청도400으로 거부됐으며 두 요청 모두 적용되지 않았습니다.
- 근거: 공식 update-data-source-properties 문서는 options에서 생략된 기존 선택값이 삭제된다고 명시합니다. 배열을 단순 분할하는 방식은 사용하지 않습니다.
- 임시 대응: 추가3속성만 PATCH하고, 승인된 신규 option을 임시 준비 page의 multi_select 값으로100개 이하씩 지정해 추가합니다. 전체 기존 option id/name/color와83개page 보존을 읽기 검증한 뒤 준비page만 archive합니다. 개인journal에 준비pageID와 단계를 보존합니다.
- 개선 아이디어: schema proposal은 선언적 검토자료이며100개초과 시 직접PATCH 실행 payload로 사용하면 안 됩니다. 향후 schema 적용 CLI에는 이 제한의 admission 검증을 추가해야 합니다.

## (2026-10-22 17:29) [Bug] Notion 선택값 정규화와 읽기 검증 호환
- 증상: 추가된 선택값 가운데 CapEx/SiCap/SoCAMM이 schema에 없다는 차단이 남았습니다.
- 근원(root cause): Notion은 이름의 대소문자·앞뒤 공백을 무시하고 기존 CAPEX/SiCAP/SOCAMM option을 재사용하지만 로컬 schema/properties 비교는 문자열 완전 일치만 사용했습니다.
- 수정: select/multi_select 비교를 동일 정규화로 통일했습니다. 서로 다른 태그 변경은 계속 CONFLICT로 검출합니다. 원본 표기와 본문은 변경하지 않습니다.
- 검증: 회귀3개가 수정 전 실패한 것을 확인했고 수정 후 관련144 tests/Ruff check·format PASS입니다. 실제 schema11속성·선택값 준비 완료, 기존83개page와 기존option id/name/color 보존 검증 완료. 이번 임시 준비page1개만 archive했습니다.
- 재발 방지 / 배운 것: 실 API의 이름 정규화와 options100개 요청 제한을 독립된 경계 동작으로 취급합니다.

## (2026-10-22 17:33) [Bug] 실제 Notion rich_text 병합과 journal 복구 검증
- 증상: 삼성전자 시험page 본문 업로드 후 read-back에서 rich_text 조각 개수가 달라 중단됐습니다.
- 근원(root cause): Notion은 같은 링크·서식의 연속 text를 병합합니다. 문자 합계는 같았지만 로컬 비교는 조각 경계까지 비교했습니다. 진단은 본문 없이 차이 경로와 길이만 보존했습니다.
- 수정: 본문 비교 시 같은 링크·서식의 인접 text를 합쳐 비교합니다. 내용·링크·서식 차이는 계속 실패합니다. logical content hash는 기존v1직렬화를 유지해 frozen manifest/journal과 호환합니다.
- 검증: 회귀가 수정 전 실패했고 관련146 tests가 통과했습니다. 동일 journal로 resume해 새page를 만들지 않고 기존 시험page1개 read-back과 최종Key확정까지 완료했습니다.
- 결과: 삼성전자 시험page https://www.notion.so/401e25c7f42181628124dca03f7b48c8 . 기존83개는 보존됐고 나머지신규34개 plan을 재생성합니다.

## (2026-10-22 17:36) [Decision] 실제 backfill과 최신 전체 검증 근거
- 선택: 시험1개 성공 후 신규34개와 그 신규target을 참조하는 시험page의RELINK1개를 같은 batch로 적용합니다. manifest blocker0. 기존83legacy는 선택하지 않았습니다.
- 이유: 신규target의pageID가 생기면 시험page의 기존literal 연결을 실제 링크로 갱신해야 합니다. 방금 만든 시험page만 새버전 완성 후 교체합니다. 사용자에게 최종URL을 다시 제공합니다.
- 자료: review-live-remaining-linked.json / journal-live-remaining.json. 초기 remaining manifest는 LINK_DEPENDENTS_MISSING으로 차단돼 적용하지 않았습니다.
- 검증: 최신 관련146 tests/Ruff PASS. 전체1558 passed /18 failed /15 deselected /2 warnings,82.69초. 실패18개는 기존과 동일한 cache권한·chart프로세스/폰트·외부금융API 환경 실패입니다. 전체PASS로 보고하지 않습니다. 로그: /tmp/notebook-notion-live-update-final-tests.log.
- 실패 이름:
  - FAILED tests/pipelines/test_brief.py::test_run_all_targets_included_and_ranked
  - FAILED tests/pipelines/test_brief.py::test_run_isolates_per_ticker_failure - ...
  - FAILED tests/pipelines/test_brief.py::test_run_macro_failure_does_not_block
  - FAILED tests/pipelines/test_brief.py::test_llm_failure_falls_back_to_rule_text
  - FAILED tests/pipelines/test_brief.py::test_stale_close_warning_propagates_to_brief_item_and_render
  - FAILED tests/pipelines/test_brief.py::test_swing_w150_line_is_reference_only
  - FAILED tests/pipelines/test_technical_contract_parity.py::test_technical_contract_is_identical_across_check_analyze_and_brief
  - FAILED tests/tools/technical/test_charting.py::test_render_technical_chart_basic
  - FAILED tests/tools/technical/test_charting.py::test_render_technical_chart_with_patterns
  - FAILED tests/tools/technical/test_charting.py::test_render_technical_chart_with_levels
  - FAILED tests/tools/technical/test_charting.py::test_render_technical_chart_empty_df
  - FAILED tests/tools/test_macro.py::test_macro_tool_execute - AssertionError: a...
  - FAILED tests/tools/test_macro.py::test_macro_tool_yield_spread - AssertionErr...
  - FAILED tests/tools/test_macro.py::test_macro_tool_fear_greed_label - Assertio...
  - FAILED tests/tools/test_news.py::test_news_tool_execute - AssertionError: ass...
  - FAILED tests/tools/test_news.py::test_news_tool_invalid_ticker - AssertionErr...
  - FAILED tests/tools/test_news.py::test_news_tool_limit - AssertionError: asser...
  - FAILED tests/tools/test_news.py::test_news_article_fields - AssertionError: a...
- ADR 후보? no

## (2026-10-22 17:41) [Bug] Notion paragraph의 빈 icon 기본값 호환
- 증상: 후속batch에서24개 본문 검증 후 한 quote 내부paragraph의icon:null때문에 중단됐습니다.
- 근원(root cause): 실제API가 일부paragraph에만 선택적빈icon필드를 추가했습니다. 본문·링크·서식은 동일했습니다.
- 수정: paragraph의icon:null은 생략과 동일하게 비교하고 실제icon값은 계속 비교합니다. logicalhash는 바뀌지 않습니다.
- 검증: 회귀가 수정 전 실패했고 관련147 tests가 통과했습니다. 같은manifest/journal의resume으로 남은page를 이어 검증합니다. 불확실한새create는 하지 않았습니다.
- 재발 방지 / 배운 것: read-back은 API가 보충하는 빈 기본값과 실제 사용자편집을 구분해야 합니다.

## (2026-10-22 17:44) [Decision] 최종 API 호환 검증 결과
- 최신 관련147 tests/Ruff check·format PASS. 전체1559 passed /18 failed /15 deselected /2 warnings,82.43초. 직전과 동일18개환경실패입니다. 로그: /tmp/notebook-notion-live-update-final2-tests.log.
- 최신 전체 실패 이름(생략 없음):
  - FAILED tests/pipelines/test_brief.py::test_run_all_targets_included_and_ranked
  - FAILED tests/pipelines/test_brief.py::test_run_isolates_per_ticker_failure
  - FAILED tests/pipelines/test_brief.py::test_run_macro_failure_does_not_block
  - FAILED tests/pipelines/test_brief.py::test_llm_failure_falls_back_to_rule_text
  - FAILED tests/pipelines/test_brief.py::test_stale_close_warning_propagates_to_brief_item_and_render
  - FAILED tests/pipelines/test_brief.py::test_swing_w150_line_is_reference_only
  - FAILED tests/pipelines/test_technical_contract_parity.py::test_technical_contract_is_identical_across_check_analyze_and_brief
  - FAILED tests/tools/technical/test_charting.py::test_render_technical_chart_basic
  - FAILED tests/tools/technical/test_charting.py::test_render_technical_chart_with_patterns
  - FAILED tests/tools/technical/test_charting.py::test_render_technical_chart_with_levels
  - FAILED tests/tools/technical/test_charting.py::test_render_technical_chart_empty_df
  - FAILED tests/tools/test_macro.py::test_macro_tool_execute
  - FAILED tests/tools/test_macro.py::test_macro_tool_yield_spread
  - FAILED tests/tools/test_macro.py::test_macro_tool_fear_greed_label
  - FAILED tests/tools/test_news.py::test_news_tool_execute
  - FAILED tests/tools/test_news.py::test_news_tool_invalid_ticker
  - FAILED tests/tools/test_news.py::test_news_tool_limit
  - FAILED tests/tools/test_news.py::test_news_article_fields
- 후속batch의35개candidate본문 검증을 모두 마쳤습니다. 각page를최종Key로승격하고 다시검증하는 단계입니다.
- ADR 후보? no

## (2026-10-22 23:07) [Decision] 실제 신규35개 반영과 최종 검증 완료
- 맥락: 사용자의 “다시 진행해” 지시 후 기존실행/journal을조회하니후속35transactions모두DONE였습니다. 중복실행하지않고최종조회만진행했습니다.
- 결과: Notion active118개, 신규35개, 기존83legacy보존. Key중복0·로컬전체Key집합일치·원본전체파일hash동일.
- 검증: apply에서속성·전체본문read-back완료. 최종hash기준plan은83LEGACY_UNVERIFIED/35UNCHANGED/선택0/blocker0. 최종plan에서는본문전체조회는반복하지않았습니다.
- 보존: 기존.serena의SHA256 40e17269250fbd4577bbe35991cde1c44010aa9d1aad5a37e1fcfabc1c49d091유지. 원본/PDF/commit/push/PR쓰기없음.
- 신규삼성전자4개를같은종목으로지정했습니다. 기존83개분류는미갱신입니다. 최종예시URL: https://www.notion.so/401e25c7f42181b9b8e3d881bd273e5f
- 자료: verification-live-final.json / review-live-final.json / journal-live-remaining.json. 이번임시준비page와시험page의이전버전만archive했습니다. source-missing자동archive는없습니다.
- 선택: 실제반영완료상태로handoff/active-context/기능문서/변경기록을갱신합니다. 다음범위는기존83legacy migration검토입니다.
- ADR 후보? no

## (2026-10-26 18:12) [Decision] Notion 원문 보관 블록 제거와 목록 열 숨김
- 맥락: 사용자가 원문중복표시제거와view목록의hash/key/source path/출처제거를지시했습니다.
- 선택: 원문Markdown은로컬에서만보존하고Notion에는읽기용본문만남깁니다. 제목/본문속코드예시는유지합니다. 요청4속성은삭제하지않고목록에서만숨깁니다.
- 코드: renderer자동Raw Markdown부록을제거하고projection을notebook-v2로갱신합니다. 과거v1manifest는재사용하지않습니다.
- 실제조회:118active/35managed이며DBview는Default view(table)한개입니다. Content Hash/Key/Source Path/출처는이미모두visible:false여서view쓰기는불필요합니다.
- 실행: 전체page루트블록을스캔해정확한Raw Markdowncaption+markdown언어의보관block만제거합니다. 남은본문·pageID·schema·원본을검증하고본문/속성이현재projection과일치하는경우에만v2hash를갱신합니다. journal복구가능하게진행합니다.
- 테스트: authoredmarkdown코드는유지하고자동부록만없는회귀를수정전실패로확인했습니다. 관련148 tests/Ruff PASS입니다.
- ADR 후보? no

## (2026-10-26 18:13) [Friction] 전체 테스트의 외부 자산 다운로드 제한
- 관련148 tests와Ruff는통과했습니다. 전체suite는1554 passed/24 failed/15 deselected/2 warnings입니다.
- 기존18개환경실패외에embedding6개가tiktoken의공개cl100k_base파일다운로드DNS제한으로실패했습니다. Notion본문renderer와무관한경로이며전체PASS로보고하지않습니다.
- 전체로그: /tmp/notebook-notion-cleanup-2026-10-26-tests.log
- 실패이름:
  - FAILED tests/pipelines/stock_report/test_embed.py::test_embed_payloads_batches_and_preserves_order
  - FAILED tests/pipelines/stock_report/test_embed.py::test_embed_payloads_dimension_guard
  - FAILED tests/pipelines/stock_report/test_embed.py::test_embed_payloads_truncates_over_token_limit
  - FAILED tests/pipelines/stock_report/test_embed.py::test_embed_payloads_uses_embed_specific_auth
  - FAILED tests/pipelines/stock_report/test_embed.py::test_embed_payloads_ignores_gateway_base_url_by_default
  - FAILED tests/pipelines/stock_report/test_embed.py::test_embed_payloads_reads_open_ai_embedding_key
  - FAILED tests/pipelines/test_brief.py::test_run_all_targets_included_and_ranked
  - FAILED tests/pipelines/test_brief.py::test_run_isolates_per_ticker_failure
  - FAILED tests/pipelines/test_brief.py::test_run_macro_failure_does_not_block
  - FAILED tests/pipelines/test_brief.py::test_llm_failure_falls_back_to_rule_text
  - FAILED tests/pipelines/test_brief.py::test_stale_close_warning_propagates_to_brief_item_and_render
  - FAILED tests/pipelines/test_brief.py::test_swing_w150_line_is_reference_only
  - FAILED tests/pipelines/test_technical_contract_parity.py::test_technical_contract_is_identical_across_check_analyze_and_brief
  - FAILED tests/tools/technical/test_charting.py::test_render_technical_chart_basic
  - FAILED tests/tools/technical/test_charting.py::test_render_technical_chart_with_patterns
  - FAILED tests/tools/technical/test_charting.py::test_render_technical_chart_with_levels
  - FAILED tests/tools/technical/test_charting.py::test_render_technical_chart_empty_df
  - FAILED tests/tools/test_macro.py::test_macro_tool_execute
  - FAILED tests/tools/test_macro.py::test_macro_tool_yield_spread
  - FAILED tests/tools/test_macro.py::test_macro_tool_fear_greed_label
  - FAILED tests/tools/test_news.py::test_news_tool_execute
  - FAILED tests/tools/test_news.py::test_news_tool_invalid_ticker
  - FAILED tests/tools/test_news.py::test_news_tool_limit
  - FAILED tests/tools/test_news.py::test_news_article_fields

## (2026-10-26 18:18) [Decision] 원문 중복 표시 정리 완료
- 결과:118개 page를 스캔해35개 page의 Raw Markdown 보관 block35개만 제거했습니다. 읽기용 본문·pageID/URL·schema·원본 전체파일·기존.serena 변경을 보존했고35개 v2 hash 갱신/read-back을 완료했습니다.
- 목록: Default view(table)한개이며 Content Hash/Key/Source Path/출처는 이미 visible:false였습니다. 마지막 재조회로 확인했고 속성 삭제나 view 쓰기는 하지 않았습니다.
- 최종계획: 현재 로컬124개/remote118개,83 LEGACY_UNVERIFIED/35 UNCHANGED/6 CREATE_CANDIDATE. 새6개는 schema·검색근거 보완 전 적용 불가이며 이번 정리에 포함하지 않았습니다.
- 검증: 관련148 tests/Ruff check·format PASS. 전체1554 passed/24 failed/15 deselected/2 warnings(앞 엔트리 환경실패 목록 참조).
- 근거: verification-remove-raw-2026-10-26.json / journal-remove-raw-2026-10-26.json / plan-remove-raw-2026-10-26.json / review-after-raw-removal-2026-10-26.json / view-cleanup-after-2026-10-26.json. 개인자료는 Git 제외·0600입니다.
- 정책: 원문은 로컬에만 보존하고 자동 부록은 다시 붙이지 않습니다. 작성된 코드 예시는 유지합니다. v1 manifest 재적용 금지이며 source-missing 자동archive/PDF업로드/commit·push·PR은 미실행입니다.
- ADR 후보? no

## (2026-10-26 18:29) [Decision] notebook 스킬에 Notion 표시 정책 반영
- 맥락: 사용자가 원문 부록 제거·목록 열 숨김 정책을 notebook 스킬에도 반영하도록 요청했습니다.
- 후보: 기존 스킬에 관련 규칙 추가 / 별도 스킬 생성
- 선택: `.agents/skills/jarvis-notebook/SKILL.md`에 로컬 원본 보존, 읽기용 본문과 작성된 코드·링크·callout·wikilink 유지, Raw Markdown 부록 미생성, 네 속성의 목록 숨김 및 schema 유지 규칙을 추가했습니다.
- 기각: 별도 스킬 생성(기존 notebook 작업 흐름에 속하는 정책).
- 검증: quick_validate.py에서 `Skill is valid!`, git diff --check PASS. 이번 변경은 스킬·상태 문서만 수정했으며 Notion·로컬 원본에 추가 쓰기는 없습니다.
- ADR 후보? no

## (2026-10-26 18:50) [Bug] PR 독립 리뷰의 본문 문자 손실 수정
- 증상: 식별자·bare URL의 내부 밑줄과 제목의 C# 끝 문자가 서식으로 해석돼 사라졌습니다.
- 근원(root cause): 단어 경계를 확인하지 않은 underscore delimiter 처리와 공백 구분 없는 heading closing hash 정규식이 원인이었습니다.
- 수정: 단어 내부 underscore를 literal로 보존하고 공백 뒤 closing hash만 제거합니다. 수정 전 회귀4개 실패·2개 통과, 수정 후 관련154개 통과를 확인했습니다.
- 재발 방지 / 배운 것: 실제 읽기용 출력의 문자열과 URL을 직접 검증하는6개회귀를 추가했습니다. 독립 재리뷰 Critical/Important 0건입니다.

## (2026-10-26 18:50) [Decision] 사용자 요청에 따른 PR·머지 진행
- 맥락: 사용자가 PR 생성·머지를 명시적으로 요청해 기존 금지 경계가 갱신됐습니다.
- 후보: 오래된 main 기준 PR / 최신 main 병합 후 PR
- 선택: 최신 main을 병합해 기존 전략 기능을 보존했습니다. 문서 충돌은 양쪽 기록을 보존했고 src/cli/main.py는 notebook 등록2줄만 추가됩니다.
- 기각: 오래된 기준 유지(최신 기능과 통합 검증 필요).
- 검증: 전체 Ruff·465파일 format·diff PASS. 비밀문자열 패턴0건, 개인 notebook/data/.env/.serena는 PR에서 제외했습니다. .serena hash는 기존 값과 같습니다.
- 환경: 최초 통합 전체 테스트는2336 passed/4 failed/1 skipped/4 deselected. 전역 subprocess mock이 최초 Matplotlib 폰트 검색을 가로채는 기존 문제였고, mock 밖에서 폰트 캐시 초기화 후 차트6개가 통과했습니다. 최종 전체 테스트를 재실행합니다.
- ADR 후보? no

private artifact는 `data/notebook-notion/review-2026-10-14.json`, `schema-proposal-2026-10-14.json`, `verification-2026-10-14.json`입니다. 개인 본문·secret 없이 metadata만 저장하며 Git에서 제외됩니다. 원본 21개 파일 읽기 전후 hash 동일, `.serena/project.yml` 초기 SHA-256 동일을 확인했습니다. 실제 Notion mutation, PDF 업로드, commit/push/PR은 0회입니다.

## (2026-10-26 18:53) [Decision] 최종 로컬 검증 및 PR #64 생성
- 맥락: 전체 코드·문서·스킬을 포함하는 PR을 생성하고 검토한 head를 main에 머지합니다.
- 후보: 검증 생략 / 로컬 전체·독립 리뷰·GitHub CI 확인
- 선택: [PR #64](https://github.com/rutesun/invest-jarvis/pull/64) 생성. 최종 전체2,346 passed/1 skipped/4 deselected/기존경고2개(97.27초), Ruff·465파일format·diff PASS, 독립 재리뷰 Critical/Important 0건을 확인했습니다.
- 기각: 검증 생략(통합 회귀 방지 필요).
- 근거: /tmp/notebook-notion-pr-final-tests.log. 제품코드 수정 없이 폰트 cache 초기화 후 표준 pytest로 통과했습니다. 최종 remote CI·merge 상태는 PR에서 확인합니다.
- ADR 후보? no
