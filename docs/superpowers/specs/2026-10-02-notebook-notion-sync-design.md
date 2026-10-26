# Notebook → Notion 안전 동기화 설계

- 작성일: 2026-10-02
- 상태: 로컬 구현·검증 완료 / 외부 적용 검토 대기 (2026-10-14 갱신)
- 대상: 로컬 `notebook/` → Notion Database `투자 노트북`
- 원칙: 로컬 노트가 source of truth(원본), Notion은 검색·열람용 projection(투영)

## 1. 목표와 경계

월별 Obsidian 노트의 각 H3 항목을 Notion page 한 개로 지속적으로 모은다. 재실행은 변경이 없는 page를 쓰지 않아야 하며, 일부 실패가 기존 page를 훼손하거나 중복 page를 남기지 않아야 한다.

2026-10-14 사용자 지시로 기존 조사 전용 경계를 로컬 구현·검증으로 갱신했다. 아래 설계 추천값으로 구현 계획·코드·테스트·read-only dry-run을 진행한다. 실제 Database schema 변경, page 생성·수정·archive, PDF 업로드, commit·push·PR은 이번 범위 밖이다. 기존 승인 대기 문구는 로컬 구현에 적용하지 않는다.

현재 재검증은 로컬 113개(`research` 99, `thoughts` 3, `trades` 11), remote active 83개, 신규 후보 30개다. 아래 Research의 112/29는 2026-10-02의 역사적 snapshot이다. [현재 인계](../../handoff/notebook-notion-sync.md)와 [구현 계획](../plans/2026-10-14-notebook-notion-sync.md)이 후속 작업 기준이다.

성공 기준은 다음과 같다.

- `trades`, `thoughts`, `research` 월별 파일을 항목 단위로 정확히 파싱한다.
- Markdown link, Obsidian callout, wikilink를 의미 손실 없이 Notion block으로 변환한다.
- dry-run에서 모든 외부 변경을 사전에 설명하고, apply 후 read-back 검증이 가능하다.
- 제목 변경, source 삭제, API 중단, schema drift(속성 구조 변경) 때 자동 archive로 데이터가 사라지지 않는다.
- 현재 83개 page와 Key 호환성을 유지한다.

## 2. Research 결과

### 2.1 저장소의 기존 Notion 경로

현재 branch의 `src/integrations/notion.py`와 `jarvis report upload`는 Daily/Screener 리포트를 날짜·Type으로 찾고, 새 page 생성 성공 뒤 기존 page를 archive한다. 이 순서는 생성 실패 때 기존 page를 보존한다. 반면 Markdown 변환기는 heading·table·divider와 단순 bold 중심이며 Markdown link, wikilink, 중첩 list를 보존하지 않는다. paragraph는 1,900자에서 잘린다.

관련 테스트는 report 파일명·중복 방지와 특수 입력에서 변환 루프가 전진하는지를 검증한다. notebook 항목 parser나 remote-aware dry-run, read-back 검증은 현재 branch에 없다.

과거 worktree branch `worktree-feature+notebook-notion-sync`에는 다음 구현이 있다.

- `36c9293`: 월별 H2/H3 parser와 골든 테스트
- `72f838b`: property·callout 변환
- `28e24e1`: Key 조회 후 create/archive sync
- `428b9b1`: `jarvis notebook sync`
- `6fb8f41`: Notion API 2025-09-03의 `initial_data_source` schema 생성 수정

이 구현이 현재 Database의 83개 page를 만든 것으로 commit 메시지와 Key 집합이 일치한다. 유용한 출발점이지만, 매 sync마다 기존 항목도 새 page로 교체하고, create 뒤 block append 실패 시 미완성 page가 남으며, link·wikilink가 실제 링크가 되지 않는 한계가 있다.

### 2.2 로컬 notebook 구조

개인 데이터는 현재 worktree가 아니라 `/Users/al03229901/Develop/My/invest-jarvis/notebook`에 있고 gitignore 대상이다.

월별 항목 수는 `research` 98, `thoughts` 3, `trades` 11로 총 112개다. research 98개 중 91개가 1,900자를 넘고, 94개에 wikilink, 93개에 Markdown link, 21개에 PDF 언급이 있다. callout은 `quote` 143, `note` 107, `warning` 95, `info` 92개다. 따라서 기존의 단순 paragraph 변환과 자르기는 원문 보존 요구를 충족하지 못한다.

월별 파일 외에 `lessons.md`와 형식이 다른 research 문서 3개가 있다. 이들은 H2/H3 의미가 월별 항목 모델과 달라 별도 page 모델이 필요하다.

### 2.3 대상 Notion Database

Notion API 2025-09-03으로 읽기 전용 조사했다. Token은 출력하거나 저장하지 않았다.

- Database: `투자 노트북`
- Data source: 1개
- 현재 property 8개: `이름`(title), `Type`(select), `Date`(date), `종목`(multi-select), `테마`(multi-select), `액션`(select), `출처`(url), `Key`(rich_text)
- `Type` option은 3종이 모두 있고, `액션` option은 현재 `매수`, `매도`만 있다.
- active page: 83개 (`research` 69, `thoughts` 3, `trades` 11)
- 날짜 범위: 2026-06-23~2026-08-28
- Key: 83개 모두 존재하고 중복 없음
- 로컬 월별 항목과 정확히 일치: 83개
- 미수집: research 29개(2026-08 3개, 2026-09 26개)
- extra/orphan page: 0개

대표 page는 research가 callout 4개와 paragraph 2개, trades/thoughts가 paragraph 1개였다. block의 link annotation은 0개여서 기존 변환이 URL·wikilink를 클릭 가능한 링크로 보존하지 않았음을 확인했다.

### 2.4 Google Drive

노트 본문에는 Google Drive URL이 없다. Drive 읽기 전용 검색에서도 투자·리서치·PDF 이름의 전용 폴더와 투자 원문 PDF는 확인되지 않았다. 따라서 기존 경로를 추정하거나 파일명을 자동 매칭하면 안 된다. 초기 동기화는 노트에 명시된 Drive link만 소비하고, PDF 업로드·이동은 별도 승인 작업으로 분리한다.

## 3. 접근안 비교

### A. 과거 branch를 그대로 복원

- 장점: 이미 83개 실 page로 검증됐고 구현량이 작다.
- 단점: 무변경 재실행도 전 page를 재생성한다. 긴 research 본문과 링크가 손실되고, 부분 실패·rename·archive 정책이 약하다.
- 판단: 지속 동기화의 안전 기준을 충족하지 못한다.

### B. 검증 가능한 단방향 projection sync — 추천

- 기존 Key와 page 모델을 유지하고, read-only plan과 content hash로 변경분만 계산한다.
- 새/변경 page는 staging page를 완성한 뒤 read-back 검증하고 기존 page를 archive한다.
- source에서 사라진 Key는 자동 archive하지 않고 후보로만 보고한다.
- 장점: 기존 83개를 재사용하고, 실패 시 기존 page를 보존하며, 실제 변경만 쓴다.
- 단점: 최소 schema 확장과 변환기 보강이 필요하다. 변경 page의 Notion URL은 교체 시 달라진다.

### C. 양방향 sync와 Notion 편집 병합

- 장점: Notion에서도 편집할 수 있다.
- 단점: 충돌 해소, authoring ownership, 삭제 의미가 복잡해지고 로컬 원본 원칙이 흐려진다.
- 판단: 현재 목적에 비해 범위가 크므로 제외한다.

## 4. 추천 page 모델과 properties

H3 항목 하나를 page 하나로 유지한다. 월 파일과 날짜 H2는 container이며 page가 아니다.

| Property | 상태 | 값 / 정책 |
|---|---|---|
| `이름` | 기존 | H3 제목 |
| `Type` | 기존 | `trades`, `thoughts`, `research` |
| `Date` | 기존 | 가장 가까운 날짜 H2 |
| `종목` | 기존 | 명시적 태그와 trades 제목에서 추출 |
| `테마` | 기존 | 액션·종목을 제외한 태그 |
| `액션` | 기존 | `매수`, `매도`, `관망`, `손절`; schema option 추가는 apply 전 검사 |
| `출처` | 기존 | 첫 번째 외부 source URL. 전체 source 목록은 본문에 보존 |
| `Key` | 기존 | `{type}/{date}#{title}`; 기존 83개와 호환 |
| `Source Path` | 추가 추천 | repo 기준 상대 경로와 section anchor. 진단·rename 검토용 |
| `Content Hash` | 추가 추천 | canonical properties + rendered block tree의 versioned SHA-256 |
| `PDF 원문` | 추가 추천 | 명시된 Google Drive `webViewLink`; 파일명 자동 추정 금지 |

`Synced At`은 Notion의 `last_edited_time`과 중복되므로 초기 범위에서 제외한다. 여러 source URL과 여러 PDF URL은 단일 URL property에 맞지 않으므로 첫 URL만 property에 두고 전체 링크는 본문에서 보존한다.

schema를 전혀 바꾸지 않는 안도 가능하지만 매 실행마다 remote block을 모두 읽고 비교해야 하며, 원본 위치·hash·PDF를 구조적으로 조회할 수 없다. 지속 운영에는 위 3개 추가 property가 더 안전하다.

## 5. idempotency와 identity

현재 Key는 호환을 위해 유지한다. content hash는 identity가 아니라 change detection(변경 감지)에만 쓴다.

- 동일 Key + 동일 hash: `UNCHANGED`, API write 0회
- 동일 Key + 다른 hash: `UPDATE_CANDIDATE`
- 동일 Key + remote hash 없음: `LEGACY_UNVERIFIED`, 자동 update 금지
- 새 Key: `CREATE_CANDIDATE`
- remote에만 있는 Key: `ORPHAN_CANDIDATE`, 자동 archive 금지
- 같은 Key가 여러 remote page에 존재: `CONFLICT`, 전체 apply 중단

제목·날짜 변경은 현재 Key에서 rename으로 인식할 수 없다. 초기 구현은 새 Key 생성과 orphan 후보 보고로 처리하고, archive는 사용자가 plan manifest를 확인한 뒤 별도 명령으로 승인한다. 로컬 항목에 UUID comment를 삽입하면 rename을 추적할 수 있지만 개인 노트를 자동 수정하므로 초기 범위에서 제외한다.

## 6. Markdown·Obsidian 변환

변환기는 문자열을 한 paragraph로 합치지 않고 block tree와 rich text를 분리해 만든다.

- paragraph, heading, bullet/numbered list, divider, table을 대응 Notion block으로 변환한다.
- `**bold**`, `*italic*`, `` `code` ``, `[label](url)`을 rich text annotation과 `href`로 보존한다.
- 2,000자 rich text 제한은 UTF-8 안전 chunk로 분할하며 자르지 않는다.
- `[!quote]`는 quote block, `[!note]`·`[!warning]`·`[!info]`는 icon이 다른 callout으로 변환한다.
- callout 내부 bullet과 link는 child block으로 보존한다.
- wikilink는 전체 entry index에서 제목을 유일하게 찾을 때만 Notion page link로 변환한다. 중복·미해결 link는 원문 표기를 보존하고 dry-run warning을 낸다.
- page가 아직 없는 wikilink가 있으므로 page 생성/확정 뒤 link를 채우는 2-pass render를 사용한다.
- 표시 변환 뒤 전체 raw Markdown을 code block으로 분할 보존한다. text는 UTF-16 2,000 units, rich_text 100개, JSON payload 크기를 함께 제한한다. 긴 table은 literal로 fallback해 무손실을 유지한다.
- hash는 실제 page ID에 종속되지 않는다. target의 신규 생성·교체 때 기존 관리 page의 참조를 transitive RELINK 후보로 표시하며 선택이 빠지면 apply를 차단한다.

Google Drive PDF는 노트에 `**원문 PDF**: [파일명](https://drive.google.com/...)`처럼 명시된 경우에만 `PDF 원문` property와 본문 link로 옮긴다. Drive file ID 또는 `webViewLink`를 저장해 폴더 이동에 견디게 하고, 사람이 보는 폴더 path는 설명용 metadata로만 취급한다.

## 7. sync 흐름과 안전 정책

### 7.1 기본 실행은 read-only plan

`jarvis notebook sync` 기본값은 쓰기 없는 remote-aware dry-run으로 둔다.

1. 대상 Database ID와 data source를 조회한다.
2. property 이름·타입을 정확히 검증한다. drift가 있으면 apply 불가로 종료한다.
3. 로컬 월별 파일을 파싱하고 Key·hash·link graph를 만든다.
4. remote Key·hash를 읽어 `CREATE/UPDATE/UNCHANGED/CONFLICT/ORPHAN` plan을 만든다.
5. 항목 본문을 출력하지 않고 count, Key, source path, warning만 표시한다.
6. machine-readable JSON manifest를 로컬 artifact로 저장할 수 있게 한다.

로컬 파싱만 필요하면 `--offline`을 제공한다. 실제 변경은 `--apply <manifest>`처럼 검토한 manifest를 명시해야 한다. 실행 시 Database ID, schema fingerprint, local input hash가 manifest와 같지 않으면 중단한다.

### 7.2 create/update

추천 방식은 create-verify-swap이다.

1. candidate page를 생성하되 기존 page는 그대로 둔다.
2. block을 100개 이하 batch로 append하고 rate limit을 지킨다.
3. page property와 전체 block tree를 다시 읽어 expected fingerprint와 비교한다.
4. 검증 성공 때만 기존 page를 archive하고 candidate를 active로 본다.
5. 검증 실패 시 기존 page를 보존하고 candidate만 실패 산출물로 보고한다. 자동 재시도·다음 항목 진행은 하지 않는다.

무변경 page는 write하지 않으므로 기존 83개의 URL과 edited time이 유지된다. 변경 page의 URL 안정성이 더 중요하다는 요구가 생기면 in-place replace를 별도 접근안으로 재검토한다. in-place는 block 삭제와 append 사이에 불완전 상태가 노출되는 단점이 있다.

### 7.3 archive와 삭제

- source에서 사라진 page를 일반 sync가 archive하지 않는다.
- `archive-missing`은 별도 plan과 명시적 apply를 요구한다.
- rename 후보는 source path·유사 제목·이전 hash로 제안만 하고 자동 확정하지 않는다.
- Notion에서 사람이 추가한 page나 Key가 없는 page는 unmanaged로 취급한다.
- 영구 삭제는 지원하지 않는다.

## 8. backfill 추천 범위

첫 apply는 월별 모델의 미수집 29개 research 항목만 대상으로 한다. 기존 83개에는 새 hash가 없고 legacy 변환으로 link·긴 본문이 손실됐을 수 있으므로 `LEGACY_UNVERIFIED`로 보고하되 변경하지 않는다.

이 수치는 2026-10-02 추천 범위다. 2026-10-14 재조회 결과 신규 후보는 30개(8월 3, 9월 26, 10월 1)로 바뀌었다. 실제 첫 apply는 최신 manifest에서 1개만 검토해 read-back/no-op 확인 후 나머지를 검토한다.

그 다음 단계에서 기존 83개를 작은 batch로 재렌더링하는 migration plan을 별도로 만든다. 각 page는 create-verify-swap을 통과한 경우에만 legacy page를 archive한다. 신규 29개 backfill과 기존 83개 재렌더링을 같은 apply에 섞지 않는다.

`lessons.md`와 standalone research 3개는 초기 backfill에서 제외한다. 각각 lesson, evergreen/reference 문서라 날짜 H2/H3 항목 계약과 다르다. 이들을 포함하려면 `monthly_entry`, `evergreen_document`, `lesson` page model을 먼저 분리해야 한다.

## 9. 검증 전략

### 정적·단위 검증

- 실제 형식을 익명화한 fixture로 raw Markdown → entry model 골든 테스트
- 1,900자 초과, nested list, 4종 callout, 다중 source, PDF link, wikilink 중복·미해결 테스트
- property 이름·타입·select option boundary contract
- 같은 입력의 hash와 plan이 반복 실행에서 동일한지 검증

### integration 검증

- mock API로 `UNCHANGED` write 0회 확인
- candidate create, block append, read-back 각 단계 실패 시 기존 page가 archive되지 않는지 확인
- duplicate Key와 schema drift에서 apply 전체가 시작되지 않는지 확인
- dry-run에서 create/update/archive API 호출 0회 확인

### 제한된 live 검증

1. read-only plan으로 83 legacy-unverified + 29 create가 나오는지 확인한다.
2. 사용자 승인 후 test page 1개만 apply하고 property·block·link를 read-back한다.
3. 같은 manifest 재실행이 stale로 거부되고, 새 plan은 83 legacy-unverified + 적용분 unchanged + 나머지 create가 되는지 확인한다.
4. 이상이 없을 때만 나머지 29개 backfill을 별도 승인한다.
5. legacy 83개 재렌더링은 새 migration plan과 별도 승인을 받아 진행한다. 모두 완료된 뒤에만 112 unchanged를 기대한다.

## 10. 열린 선택지와 추천

가장 먼저 정할 선택은 Database schema 확장이다.

- 최소 확장(추천): `Source Path`, `Content Hash`, `PDF 원문`을 추가한다. no-op 판단, 원본 추적, Drive link 조회가 명확해진다.
- 현 schema 유지: 외부 변경이 적지만 매번 block 전체 비교가 필요하고 PDF·원본 위치가 본문에만 남는다.
- 새 Database: 기존 83개를 보존한 채 새 모델을 시험할 수 있으나 Database가 분산되고 다시 backfill해야 한다.

2026-10-14의 로컬 구현 기본값으로 최소 확장을 채택했다. schema 적용 승인은 아직 포함되지 않으며 Database 변경은 수행하지 않았다. 종목·테마의 신규 multi-select option도 별도 schema proposal에 포함해 page create 시 암묵적 schema 변경을 차단한다.

## 11. ADR 후보

- 로컬 notebook을 authoring source로 두고 Notion을 단방향 projection으로 운영한다.
- 일반 sync는 source에 없는 remote page를 자동 archive하지 않는다.
- 변경 적용은 create-verify-swap으로 기존 page를 검증 완료까지 보존한다.

이 항목들은 구현 범위가 승인된 뒤 ADR 채택 여부를 결정한다.


## 2026-10-22 종목별 보기 보완
기존 `종목` multi-select를 공유 키워드로 사용합니다. 사용자 정정에 따라 수동 종목 대응표를 폐기하고 Naver 종목 검색 API의 국가·시장·code와 반환된 이름을 근거로 통일합니다. 다종목 항목은 모든 확인된 종목을 지정합니다. `stock_groups`는 예정 분류이며 legacy의 remote 속성은 변경하지 않습니다. 모호한 결과·짧은 ticker/theme 충돌·ETF 부분 일치는 검토 대상으로 둡니다. research의 제목·본문 단순 언급은 자동 분류하지 않습니다. 사용자가 검색어 전송 범위를 명시 승인한 뒤542개 조회를 완료했습니다. 작업 중 원본에 추가된 새1항목은 이번 계획에서 제외했으며 최신 검토 범위와 다음 단계는 handoff를 따릅니다.

## 2026-10-26 원문 표시 정책 갱신
사용자가 Notion의 원문 중복 표시 제거와 목록에서 Content Hash/Key/Source Path/출처 숨김을 지시했습니다. 위 raw Markdown 부록 설계는 이력으로 남기며, 현재는 원본을 로컬에 보존하고 Notion에는 읽기용 본문만 제공합니다. 작성된 코드 예시는 유지합니다. Projection/hash는 notebook-v2로 갱신하고 기존 pageID와 본문을 보존하며 원문보관block만 제거합니다. 목록 속성은schema에서삭제하지않습니다.
