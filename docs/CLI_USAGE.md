# CLI 사용 가이드

## 실행 방법

### 방법 1: uv run 사용 (권장)
```bash
uv run jarvis check AAPL
uv run jarvis analyze AAPL
uv run jarvis brief --no-llm
uv run jarvis report
```

### 방법 2: Shell Alias (더 짧게)
`~/.zshrc` (또는 `~/.bashrc`)에 추가:
```bash
alias jarvis="uv run jarvis"
```

적용:
```bash
source ~/.zshrc
```

이후 짧게 사용:
```bash
jarvis check AAPL
jarvis analyze AAPL
jarvis report
```

---

## 명령어 상세

### 공통 Quality와 전략별 수량 (`check` / `analyze` / `brief`)

기존 세 명령에 공통 사실·Quality와 전략별 Position Plans(목표·매수·매도 수량)를 표시합니다. 독립 `score` 명령은 제공하지 않습니다.

```bash
uv run jarvis check AAPL
uv run jarvis check AAPL --detail-strategy
uv run jarvis analyze AAPL
uv run jarvis brief
```

기본 출력은 현재 상태 → Quality·4축·미공개 사유 → 주요 가격대 → 최근 5거래일과 핵심 변화 → 전략별 대응·수량 순서입니다. 돌파·지지·회복 기준은 현재 유효한 실측이 있을 때 표시하고, 종료된 진입의 옛 가격은 과거 구조 참고로 구분합니다. 5거래일 표의 기술점수는 기존 Technical Score이며 현재 Quality와 별도입니다. Quality는 각 날짜 원점에서 재계산하며 장중값·미산출을 구분합니다. 과거·해소·무효화 이력은 `--detail-strategy`에서 전체 FactRef(사실 참조) 및 전략 채택·거절 audit와 함께 확인합니다. 현재 유효한 ACTIVE 상태는 발생한 지 20세션이 지났어도 표시하며, 당일 판정의 과거 source 근거와 미평가 경고는 유지합니다. Quality는 실험적 상태 지수이며 기존 Technical Score·매매판정·brief 순위를 바꾸지 않습니다. 연속 FINAL 252봉과 입력 완전성을 충족하지 못하면 null과 이유를 표시합니다. 미완성 봉은 PROVISIONAL/preview로 구분합니다.

Quality의 canonical 2년 원점이 부족할 때 기존 공급자의 `3y` 입력을 최대 한 번 보충합니다. 보충 시세는 Quality에만 사용하고 겹치는 유효 OHLCV가 다르면 Quality를 unavailable로 표시합니다. 기존 전략 입력·점수는 유지합니다. 과거 봉 FINAL은 기존 supplied-chart 추론 규약이며, live range API의 `STUB_ONLY` 검증 상태를 바꾸지 않습니다.

`TECHNICAL_LEGACY`, `PLAYBOOK_V1`, `SWING_W150`의 계획은 같은 실제 보유·계좌 입력에 대한 독립 대안입니다. 수량을 합산하지 않습니다. 보유 설정 읽기가 실패하면 미보유 0주로 처리하지 않고 수량 미정과 오류를 표시합니다. 매수의 자본·위험 예산·주당 위험·시세·실행 확인이 부족하면 수량은 unavailable입니다. 주문이나 계좌 설정 쓰기는 수행하지 않습니다.

### check - 텍스트와 기술 차트 HTML

```bash
# 기본 텍스트
uv run jarvis check ALAB 161890

# 텍스트 + HTML 자동 저장, 저장 경로와 파일 링크 출력
uv run jarvis check ALAB 161890 --html

# HTML 저장 경로 직접 지정
uv run jarvis check ALAB 161890 --html reports/check.html

# 전체 전략 근거와 점수 이력을 텍스트로 출력하고 HTML 상세도 펼쳐 저장
uv run jarvis check ALAB 161890 --detail-strategy --detail-history \
  --html reports/check-detail.html

# 기존 보고서를 교체할 때만 명시
uv run jarvis check ALAB 161890 --html reports/check.html --force

# 사용 가능한 옵션 확인 (시세 조회 없음)
uv run jarvis check --help
```

#### 출력 읽는 법과 저장 동작

`check` 기본 화면은 현재 유효 상태와 최근 20개 응답 거래일의 관찰 흐름을 먼저 연결합니다. 현재 상태의 시작·조건 충족 사건은 기간 밖이어도 포함하고, 같은 회복을 설명하는 `이탈 관찰 종료`와 `회복 확인`은 합칩니다. 점수 추이는 기존 5일 범위를 유지합니다. 예를 들어 `150일선: 청산 조건 충족 후 미회복`은 과거 조건 충족과 현재 상태를 뜻합니다. `오늘 신규 매매 지시 없음 · 보유 수량 유지`와 함께 표시될 수 있으며 실제 매도 완료나 새로운 매도 수량을 뜻하지 않습니다.

`--html`은 기본 텍스트를 출력한 뒤 UTF-8 HTML을 추가 저장합니다. 경로를 생략하면 실행한 디렉터리의 `tmp/reports/check-<시각>-<고유ID>.html`에 매번 새 파일을 만듭니다. 저장 후 절대경로와 복사 가능한 `file://` 링크를 출력합니다. 경로를 직접 정할 때는 `--html reports/check.html` 또는 `--html=reports/check.html`을 사용합니다. 종목은 `--html` 앞에 적습니다. 바로 뒤의 일반 인자는 저장 경로로 해석합니다. `--html` 옵션 전체를 생략하면 텍스트만 출력하고 보고서 파일·폴더를 만들지 않습니다.

여러 종목을 입력 순서대로 한 파일에 담고, `analyze`의 기술 차트를 같은 실행 데이터로 생성해 내장합니다. 외부 CDN·서버 없이 파일을 옮겨 열 수 있으며 자동으로 브라우저를 열지 않습니다. 추가 뉴스·LLM 조회는 없고, HTML 요청 시 로컬 차트 렌더 시간과 파일 크기가 더해집니다. 기존 이름→티커 해석 경로는 유지됩니다.

차트 위의 브리핑은 추세·가격 위치·가격 구조·cRSI·거래량과 이동평균 네 개를 요약합니다. 상승/위쪽 수치는 초록, 하락/아래쪽은 붉은색, 과매도는 별도 상태색입니다. 이동평균 방향은 선 자체의 최근 21봉 변화이고 주가 이격과 구별합니다. cRSI는 가변밴드를 사용하며 거래량 비중은 최근 20개 응답 봉의 상승일·하락일 기준(보합 제외)입니다. 50/200의 현재 배열과 실제 교차 사건 날짜를 구분하고 기준일·잠정 여부·미산출 사유를 함께 표시합니다.

HTML 상단의 `현재 상태`에서 기준일과 핵심 세 항목을 먼저 확인합니다. 각 항목의 `이 상태가 된 경과 보기`를 펼치면 회복·재이탈·조건 충족 날짜를 읽을 수 있습니다. 추가 현재 상태와 `지난 관찰 전체 보기`는 기본 접힘이며 현재 청산 상태 확인 불가·잠정·미평가 경고는 바로 표시합니다. 기본 텍스트의 현재 상태·관찰 흐름은 유지합니다.

차트 아래의 전략 카드는 판단·보유→목표·매수/매도 수량을 함께 보여줍니다. 각 전략은 독립 대안이므로 수량을 합산하지 않습니다. Quality 선 그래프는 최근 5거래일이며 4축 막대는 표시된 평가일 기준입니다. 확정 총점과 장중 잠정 축의 날짜가 다를 수 있습니다. 날짜별 수치와 보조 위험의 세부 근거는 펼쳐서 확인하며 현재 위험 수준·미평가·데이터 경고는 기본 화면에서 확인할 수 있습니다.

출력 경로와 기존 파일 충돌은 시세 조회 전에 확인합니다. 기존 파일은 `--force`가 있어야 교체하며 `--force` 단독 사용은 오류입니다. 저장 실패 시 기존 파일을 보존합니다. 종목 일부가 실패하면 성공 결과와 실패 사유를 함께 저장하고 exit 1로 종료합니다. 차트만 실패하면 경고와 분석 결과를 남깁니다. `--detail-history`, `--detail-strategy`는 텍스트와 HTML 모두에 적용되며 HTML의 상세 근거는 펼쳐서 볼 수 있습니다.

HTML의 구조화된 가격·이동평균은 종목 통화에 맞춰 표시합니다. 상세 technical 진단 원문에는 국내 가격에도 기존 `$` 기호가 남을 수 있습니다. 이는 원문 보존에 따른 표시 제한이며 실제 USD 단위를 뜻하지 않습니다.

### notebook sync - 투자 notebook 지속 동기화

기본 실행은 Notion API `2025-09-03`으로 지정 Database를 읽는 remote-aware dry-run입니다. `.env`의 `NOTION_TOKEN`을 사용하며 리포트용 `NOTION_DATABASE_ID`와 별개로 `--database-id`를 지정합니다. 기본 대상은 투자 notebook Database입니다.

```bash
# 로컬 파싱·변환만 확인 (Notion 접근 없음)
uv run jarvis notebook sync --offline \
  --notebook-dir /Users/al03229901/Develop/My/invest-jarvis/notebook \
  --manifest data/notebook-notion/offline.json

# schema, active page, hash, duplicate를 읽기 전용으로 확인
uv run jarvis notebook sync \
  --notebook-dir /Users/al03229901/Develop/My/invest-jarvis/notebook \
  --database-id eee67e454ce4478b9f1749e8e92a1b42 \
  --manifest data/notebook-notion/review.json
```

`--manifest`에는 본문 없이 Key·source path·hash·page ID·schema 제안·선택 목록이 저장됩니다. 개인 metadata가 있으므로 `data/`의 gitignore를 유지하고 외부 공유하지 않습니다. 기존 manifest를 덮어쓰지 않으며 원본 안에는 artifact를 저장할 수 없습니다. schema 변경 등 blocker가 있으면 manifest를 남긴 뒤 exit 2로 종료합니다. 쓰기는 0회입니다.

종목별 검토는 기존 `종목` multi-select를 사용합니다. 수동 종목 대응표는 사용하지 않습니다. 기본 dry-run은 Naver 종목 검색 API(`ac.stock.naver.com/ac`)에 종목·태그·매매 제목에서 추출한 종목명만 보내고, 응답의 국가·시장·코드를 기준으로 같은 종목을 연결합니다. 국내는 반환된 이름, 미국은 반환된 ticker를 표시합니다. 본문·문서 제목 전체·출처 URL은 검색 API로 보내지 않습니다. 국내 부분 일치는 basic API로 주식/ETF 종류를 추가 검증합니다.

`--stock-cache PATH` 기본값은 `data/notebook-notion/stock-search-cache.json`입니다. 검색 근거는 version 2·30일 유효기간으로 저장하며 조회 성공분을 증분 저장해 장애 후 재사용합니다. API 장애·응답 형식 변경을 미검색으로 숨기지 않습니다. 검색 후보가 여러 개이거나, 짧은 영문 태그(예: HBM)가 ticker와 충돌하거나, 일반 태그가 ETF에 부분 일치하면 `stock_resolution.issues`에 검토 대상으로 남깁니다. 명시한 종목 미해결·cache 미조회는 blocker입니다. 미검색 일반 태그는 테마로 유지합니다. research 제목·본문의 단순 종목 언급은 검색하지 않습니다.

`--offline`은 외부 접근 없이 저장된 검색 근거만 사용합니다. 유효한 근거가 없으면 미완료 미리보기를 저장하고 exit 2로 종료합니다. `stock_groups`는 legacy·미선택을 포함한 **로컬 예정 분류**이며 현재 Notion 분류가 아닙니다.

```bash
# 이미 확인한 공개 API 샘플 근거만 사용한 부분 미리보기 (추가 외부 전송 없음)
uv run jarvis notebook sync --offline \
  --notebook-dir /Users/al03229901/Develop/My/invest-jarvis/notebook \
  --stock-cache data/notebook-notion/public-samples-cache-api-v2-2026-10-22.json \
  --manifest data/notebook-notion/offline-api-new.json

# 저장된 예정 분류의 삼성전자 문서 목록
uv run python -c 'import json; p=json.load(open("data/notebook-notion/review-api-partial-v2-2026-10-22.json")); print("\n".join(p["stock_groups"].get("삼성전자", [])))'
```

`review-api-complete.json` 등 과거 자료는 승인 당시542개 검색어/117항목의 이력입니다. 2026-10-22 실제 업데이트 지시 후 최신118항목으로 범위를 갱신했습니다. 최신 적용·검증 자료와 현재 상태는 [인계](handoff/notebook-notion-sync.md)를 확인하세요. 과거 manifest는 적용하지 않습니다.

apply는 검토 manifest의 `stock_resolution` 근거를 재현하고 검색 API를 새로 호출하지 않습니다. 신규 apply는 만료 근거를 차단합니다. `--resume`은 부분 실패 복구를 위해 만료된 frozen evidence도 재현하되 기존 schema/remote/journal 검증은 유지합니다. 검색 근거가 없는 과거 정적 분류 manifest는 거부합니다.

기본 후보는 신규 항목뿐입니다. `--only-key 'research/YYYY-MM-DD#제목'`을 반복해 범위를 좁힐 수 있습니다. `--include-updates`는 hash가 있는 변경 및 `RELINK_CANDIDATE`(새 target ID로 링크 재연결이 필요한 page)도 포함합니다. 참조 page 선택이 빠지면 apply가 차단됩니다. legacy migration과 orphan archive는 지원하지 않으며 별도 설계·승인이 필요합니다.

schema 변경과 실제 page 적용 승인을 받은 **다음** 최신 schema로 새 manifest를 생성합니다. 첫 적용은 1개 항목으로 검증한 후 나머지 backfill을 검토합니다. 같은 대화에서 이미 승인된 범위에는 승인 질문을 반복하지 않습니다.

`schema_proposal`은 필요한 최종 schema를 설명하는 검토 자료이며 그대로 API에 전송할 수 있는 실행 보장은 없습니다. Notion의 select/multi_select options 요청 배열은100개 이하이며, schema 수정에서 생략한 기존 option은 삭제됩니다. 큰 배열을 단순 분할해 PATCH하지 마세요. 이번 실제 반영에서는3속성만 추가한 뒤 승인된 신규 선택값을 임시 준비page의 값으로100개 이하씩 추가하고, 기존 option과page 보존 검증 후 준비page만 archive했습니다. 이 준비 절차는 현재 CLI의 자동 기능이 아닙니다.

선택값은 Notion과 같이 대소문자·앞뒤 공백을 무시하고 비교합니다. 본문 read-back은 같은 링크·서식의 연속 text 병합과 paragraph의 빈 icon 기본값을 허용하되, 내용·링크·서식 변경은 계속 차단합니다. 2026-10-26부터 원문은 로컬 notebook에만 보존하고 Notion에 Raw Markdown 부록을 붙이지 않습니다. 이 표시 변경의 projection/hash version은 `notebook-v2`이며 과거 v1 manifest를 재적용하지 않습니다. `Content Hash`, `Key`, `Source Path`, `출처`는 목록 보기에서 숨기되 속성 자체는 유지합니다.

```bash
# 아래 명령은 외부 쓰기를 수행하므로 별도 적용 승인 후에만 실행
uv run jarvis notebook sync \
  --notebook-dir /Users/al03229901/Develop/My/invest-jarvis/notebook \
  --apply data/notebook-notion/approved-one.json \
  --journal data/notebook-notion/approved-one.journal.json

# 부분 실패 복구: 동일한 manifest와 journal을 유지
uv run jarvis notebook sync \
  --notebook-dir /Users/al03229901/Develop/My/invest-jarvis/notebook \
  --apply data/notebook-notion/approved-one.json \
  --journal data/notebook-notion/approved-one.journal.json --resume
```

`CREATE_PENDING` 상태에서 staging Key를 재조회해 유일한 page가 확인되면 재사용합니다. 0개 또는 여러 개면 수동 확인이 필요하며 자동 재생성하지 않습니다. append는 remote 본문의 prefix(이미 저장된 앞부분)를 확인한 뒤 남은 부분만 채웁니다. Notion 쓰기에는 자동 retry가 없습니다. 새 계획을 만들기 전에 기존 journal을 먼저 복구하세요. `--offline` 결과는 적용할 수 없습니다.

이번 worktree의 sandbox에서는 uv cache를 `--cache-dir /tmp/notebook-notion-uv-cache`, Matplotlib cache를 `MPLCONFIGDIR=/tmp/notebook-notion-mpl`로 지정해 검증했습니다.

### 1. check - 빠른 기술적 분석 (다중 티커)

**특징:**
- LLM 불필요 (빠른 응답)
- 공통 3년 데이터 기반 8개 컴포넌트 분석 (SMA 100·200 방향 포함)
- 주요 기술 지표만 출력, Macro 미포함
- 여러 티커를 한 번에 전달 가능 (일부 실패해도 나머지는 계속 출력)

**사용법:**
```bash
uv run jarvis check <TICKER> [TICKER ...]
```

**예시:**
```bash
# 단일 티커
uv run jarvis check AAPL

# 여러 티커 한 번에 (한국·미국 혼합 가능)
uv run jarvis check AAPL MSFT 005930.KS
```

---

### 차트 상태 점수와 최근 5거래일

`check`·`analyze`·`brief`의 기본 화면에서 신규 Quality 총점·4축의 의미·실측 근거·전일차를 확인합니다. 최근 5거래일 표는 신규 Quality(0~100)와 기존 Technical Score를 구분하고, 핵심 변화에는 확정 기간의 총점·4축 변화와 날짜별 관찰·전략 신호를 함께 표시합니다. 장중 일봉은 현재가격으로 표시하며 확정 점수와 구분합니다. 공개 조건을 충족하지 못한 진단값을 정상 점수로 대신 표시하지 않습니다.

구조 위험은 발생일·첫 확정일·현재 평가일을 구분합니다. 이탈 후 회복하고 다시 이탈하면 새 연속 구간의 시작일을 표시합니다. 기본 화면은 신호 이름·날짜·가격 기준을 보여주며 내부 source ID와 원시 근거는 `--detail-strategy`에서 확인합니다.

### EntryOpportunity와 구조 위험 진단

`check`, `analyze`, `brief`의 공통 기본 출력에 신규 진입 상태, 이유, source Signal·발생일·경과 거래일, Production policy와 별도 구조 위험도를 표시한다. `EXECUTION_WATCH`는 기존 내부 `WATCH`의 사용자 표시다. `ALLOW + CAUTION/HIGH_RISK`는 기존 진입 조건을 통과했으나 연구상 구조 경고가 함께 있다는 뜻이며, 위험도 자체가 진입 차단·매도 지시는 아니다. 장중은 `PROVISIONAL`, 완료된 차트는 `FINAL`로 구분한다.

현재 대표 source의 판단은 기본 `data/research/entry-shadow.jsonl`에 실행할 때마다 추가 기록한다. 경로는 `JARVIS_ENTRY_SHADOW_LOG_PATH` 환경변수로 바꿀 수 있다. Strategy는 이 파일을 읽지 않으며 삭제해도 같은 차트의 계산 결과는 같다. 저장 실패는 별도 경고로 표시하고 기존 진입 판정은 유지한다. 자동 일일 스케줄·과거 날짜 backfill·미래 수익률 계산은 추가하지 않았다.

```bash
uv run jarvis check ALAB COHR INTC NVDA AMD
JARVIS_ENTRY_SHADOW_LOG_PATH=data/research/my-entry-shadow.jsonl uv run jarvis check NVDA
```

JSONL은 갱신형 DB가 아닌 분석용 평가 snapshot이다. 반복 실행·장중/종가·서로 다른 policy/parameter 기록을 삭제하거나 덮지 않는다. 분석 시 source·차트 거래일·policy/parameter·finality를 구분하고 동일 판단의 중복 snapshot은 선택 기준을 명시해 처리한다. 기록에 실제 보유 수량·주문·손절·미래 outcome은 포함하지 않는다. 프로그램에서 `AnalysisStrategyService(shadow_recorder=None)`으로 기록만 끌 수 있으며, `StrategyRunner(shadow_enabled=False)`는 Shadow 계산을 끄고 Production 결과는 유지한다.

Trading Observation v1은 기본 ON이며 공통 출력에서 cycle/support, 현재 SETUP·Positive/Risk EPISODE, 당일 EVENT를 보여준다. 최근 20거래일 Observation·Signal history와 과거·종료된 전체 이력은 `--detail-strategy`에서 확인한다. WATCH는 지지 관찰이며 신규 매수 허용을 뜻하지 않는다. 기본 출력에서 날짜·가격·판단 Evidence를 확인하고 `--detail-strategy`에서 설정·fingerprint와 재현 정보를 추가로 확인한다. 기본 ON과 detector별 설정 선정은 별개다. 거래량 확장·수축 ratio는 미선정이므로 기본 실행에서 해당 항목은 `UNRESOLVED`/미평가이며, 평가 실패·Observation OFF와도 구분한다.

기본 Pullback은 `SWING_W150_V2_PARAMS_V1`이다. support ladder V2는 failure/restart 미선정으로 기본 CLI에서 활성화되지 않으며, 아래 offline 연구 명령에서 사전 고정된 진단 설정으로만 비교한다. 이 명령은 provider/LLM/실계좌와 연구 JSONL을 사용하지 않는다.

```bash
# 보존한 baseline의 예상 파일 집합·hash와 현재 V1 결과를 검증
uv run python scripts/research_trading_observations.py verify-baseline \
  --output tmp/trading_observation_v1/baseline

# A: 같은 정책의 Observation ON/OFF, B: V1 / 명시 V2 진단 비교
uv run python scripts/research_trading_observations.py compare \
  --baseline tmp/trading_observation_v1/baseline \
  --protocol research/trading_observation_v1/protocol.json \
  --output tmp/trading_observation_v1/comparison-new

# 과거 로컬 실제 OHLCV에서 후보 탐색 후 제한된 prefix의 adapter/renderer 재현
uv run python scripts/research_trading_observations.py cases \
  --protocol research/trading_observation_v1/protocol.json \
  --output tmp/trading_observation_v1/cases-new
```

`compare`/`cases`는 보존 증거를 덮지 않도록 새 output 디렉터리를 요구한다. 비교는 전체 기간 replay를 포함해 오래 걸릴 수 있고, 종목 완료 시 진행 상태를 출력한다. 결과의 `RESEARCH_ONLY_NOT_PRODUCTION_DEFAULT`·전체 설정·fingerprint와 원자료/실행코드 hash를 함께 확인한다. [현재 검증 범위와 제한](references/2026-10-21-trading-observation-v1-validation.md)을 참고한다.

---

### 2. analyze - 심층 분석 (LLM)

**특징:**
- 공통 3년 기술 분석 + 뉴스·재무·공시·수급·Macro 통합
- 액션·타이밍은 규칙(`decision_summary`)이 확정 — LLM은 그 결정을 **설명만** 하고 새 액션을 만들지 않음
- 최종 LLM에 모든 소스와 고정 decision을 한 번에 전달해 `종합 해설` 생성

**요구사항:**
- `OPENAI_API_KEY` 필요 (LLM 모델은 `config.yaml` `llm:` 섹션에서 설정)

**사용법:**
```bash
uv run jarvis analyze <TICKER>
```

**예시:**
```bash
uv run jarvis analyze AAPL
uv run jarvis analyze 005930.KS
```

**출력 내용:**
- Macro 스냅샷 (VIX·Fear&Greed·WTI·US 10Y/2Y·10Y-2Y Spread·DXY) — Analyze/Brief 전용
- 상단 판단 요약
  - `주도 팩터`
  - `핵심 변수` (짧은 headline 기준)
  - `액션` (규칙이 확정 — Playbook veto가 반영된 최종 값)
  - 판단이 약하면 `판단 보류`와 이유 표시
- 구조 레벨
  - 장기 구조 구간 기준 `수요 존 / 공급 존 / 무효화 기준`
  - zone(구간) 중심으로 표시
- 실행 레벨
  - `pivot / 이동평균선 / 기타 단기 보조선` 중 가까운 순서로 표시
  - 진입/확인/리스크 관리용 line 정보
- 팩터 분류
  - `주도 / 보조 / 참고`
  - 각 팩터별 이유(`role_reason`) 표시
  - `참고`는 왜 참고로 내렸는지 함께 표시
- 액션 시나리오
  - `기본 시나리오`
  - 가격 레벨(`최근 지지/저항 + 50/150일선`) / 확인 조건 / 무효화 조건 / 대응
- 원시 데이터
  - 가격 및 변동률
  - 기술적 분석 요약과 핵심 인사이트
  - 뉴스 감성 분석 / 영향 평가 / 주요 테마
  - **공시 분석** (최근 3개월 주요 공시, SEC/DART)
  - **수급 동향** (외인/기관 1d/5d/10d 순매수, 한국주식 전용)
  - **종합 해설** (모든 소스 + 고정 decision 설명 — 근거 / 리스크 / 모니터링 포인트, 새 액션 생성 안 함)
  - **차트 시각화**: 기술적 차트 PNG 자동 생성 (`charts/` 디렉토리)
  - 캔들스틱 + MA 라인 (20/50/150/200일)
  - Supertrend 추세선
  - 거래량 + MACD + RSI 패널
  - 패턴 마커 및 지지/저항선 표시

**출력 순서:**
1. 판단 요약
2. 팩터 분류
3. 액션 시나리오
4. 구조 레벨
5. 실행 레벨
6. 원시 데이터

구조 레벨은 장기 구조 구간이고, 실행 레벨은 pivot / MA / 패턴 기반 단기 실행 보조선입니다.

**선택 환경변수:**
- `OPENDART_API_KEY`: 한국주식 공시 조회 (없으면 공시 섹션 생략)
- `KIS_APP_KEY` / `KIS_APP_SECRET`: 한국주식 수급 + 펀더멘털 조회 (없으면 일부 한국주식 데이터 fallback 또는 생략)
  - KIS 재무 API는 엔드포인트별 재시도 후 부분 성공 데이터를 우선 사용

---

### 3. report - 일일 시장 리포트

> 다중 티커 기술 스냅샷은 `jarvis check <TICKER ...>`로 대체되었습니다 (아래 `check` 참고).

#### 3-1. report daily - 텔레그램 기반 일일 리포트

**특징:**
- 텔레그램 채널 메시지 자동 수집 및 분석
- MapReduce 패턴 5단계 파이프라인 (Ingest → Map → Shuffle → Reduce → Wrapup)
- 테마별 클러스터링 및 투자 인사이트 추출
- Claude Haiku 4.5 사용으로 비용 최적화
- `reports/YYYY-MM/daily_YYYY-MM-DD.md` 자동 저장
- Notion Database 연동 지원 (선택)

**요구사항:**
- 텔레그램 데이터 필요: `uv run jarvis telegram fetch <날짜>` 먼저 실행
- `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` 필요
- Notion 업로드 시: `NOTION_TOKEN`, `NOTION_DATABASE_ID` 필요 ([설정 가이드](../README_NOTION.md))

**사용법:**
```bash
uv run jarvis report daily [날짜] [OPTIONS]
```

**옵션:**
- `날짜`: 분석할 날짜 (YYYY-MM-DD). 미지정 시 전날
- `--data-dir, -d`: 데이터 디렉토리 (기본값: data)
- `--notion`: Notion에 업로드

**예시:**
```bash
# 전날 리포트 (MD 파일만 저장)
uv run jarvis report daily

# 특정 날짜 리포트
uv run jarvis report daily 2026-04-17

# Notion에도 업로드
uv run jarvis report daily 2026-04-17 --notion
```

**워크플로우:**
```bash
# 1. 텔레그램 메시지 수집 (먼저 실행 필요)
uv run jarvis telegram fetch 2026-04-17

# 2. 일일 리포트 생성
uv run jarvis report daily 2026-04-17
```

**출력 파일:**
- `reports/2026-04/daily_2026-04-17.md`

**리포트 구조:**
- 매크로 데이터 (VIX, Fear & Greed, 시장 지수, 환율)
- 핵심 인사이트 3-5개 (테마 간 관계 + 매크로 연결)
- 카테고리별 테마 분석
  - 투자 인사이트 테마명 (20-40자, 방향성 명확)
  - 이모지 + 요약 + 영향 + 관련 종목
  - 검색 키워드 (종목명, 기술용어, 트렌드)

**예시:**
```markdown
## 매크로 데이터
VIX: 15.2 | Fear & Greed: 65 (Greed)
미국: S&P500 +1.2%, NASDAQ +1.5% | 한국: KOSPI +0.5%

## 핵심 인사이트
💡 AI 인프라 투자 확대가 HBM 수요 증가로 이어지며 국내 반도체 업사이클 기대
🌊 미국 금리 인하 기대감 속 성장주 중심 랠리, 한국은 실적 검증 단계
⚠️ 중국 경기 둔화 우려가 이차전지·조선 섹터 리스크로 작용

## 반도체
### 🚀 GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜
...
```

**스테이지별 테스트:**
```bash
# 전체 파이프라인 한번에
./scripts/test_daily_report_stages.sh 2026-04-17

# 개별 스테이지 실행
uv run python -m src.pipelines.daily_report.stages.ingest_stage 2026-04-17
uv run python -m src.pipelines.daily_report.stages.map_stage 2026-04-17
uv run python -m src.pipelines.daily_report.stages.shuffle_stage 2026-04-17
uv run python -m src.pipelines.daily_report.stages.reduce_stage 2026-04-17
uv run python -m src.pipelines.daily_report.stages.wrapup_stage 2026-04-17
```

**상세 테스트 가이드:** [scripts/README_TESTING.md](../scripts/README_TESTING.md)

---

#### 3-2. report daily-v2 - Stock Report Engine V2 실행 (Phase 1)

**특징:**
- LLM semantic extraction 기반 `canonical_summary`/`evidence_items` 생성
- `taxonomy_path` 기준 카테고리/테마 정규화
- `reports/YYYY-MM/daily_v2_YYYY-MM-DD.md` 저장

**요구사항:**
- 텔레그램 데이터 필요: `uv run jarvis telegram fetch <날짜>` 먼저 실행
- `OPENAI_API_KEY` 필요 (LLM 모델은 `config.yaml` `llm:` 섹션에서 설정)
- Postgres 연결 필요 (`STOCK_REPORT_DB_DSN` 또는 `DATABASE_URL`)

**사용법:**
```bash
uv run jarvis report daily-v2 [날짜] [OPTIONS]
```

**옵션:**
- `--data-dir, -d`: 데이터 디렉토리 (기본값: data)
- `--config-path`: stock report 설정 파일 경로 (기본값: config.yaml)
- `--taxonomy-path`: taxonomy vocabulary 파일 경로 (기본값: config/stock_report_vocabulary.yaml)
- `--preview-limit`: canonical_summary 미리보기 개수 (기본값: 12)
- `--google-grounding / --no-google-grounding`: 기본 경로와 함께 Gemini Google Search Grounding 실험 경로(T09-B)도 실행, `daily_v2_DATE.google.md` 추가 저장 (기본값: 끔, `GOOGLE_API_KEY` 필요)

**예시:**
```bash
# 기본 실행
uv run jarvis report daily-v2 2026-05-19

# taxonomy 교체 + preview 확장
uv run jarvis report daily-v2 2026-05-19 \
  --taxonomy-path config/stock_report_vocabulary.yaml \
  --preview-limit 50

# 기본 경로 + Google grounding 실험 경로 동시 실행
uv run jarvis report daily-v2 2026-05-19 --google-grounding
```

---

#### 3-3. report daily-v2-google - DB 데이터로 Google Grounding 리포트만 생성 (T09-B 단독)

**특징:**
- DB에 이미 적재된 `knowledge_chunks`만 사용 — ingest/classify 단계를 생략한다
- Gemini Google Search Grounding 경로만 단독 실행 (기본 합성 경로는 돌리지 않음)
- `reports/YYYY-MM/daily_v2_YYYY-MM-DD.google.md` 저장

**요구사항:**
- `GOOGLE_API_KEY` 필요 (Gemini)
- Postgres 연결 필요, 해당 날짜 chunk가 이미 적재돼 있어야 함

**사용법:**
```bash
uv run jarvis report daily-v2-google [날짜]
```

**예시:**
```bash
# 어제 날짜 (인자 생략 시 전날)
uv run jarvis report daily-v2-google

# 특정 날짜
uv run jarvis report daily-v2-google 2026-05-28
```

---

#### 3-4. report upload - 기존 리포트 일괄 업로드

**특징:**
- `reports/` 디렉토리의 기존 MD 파일을 Notion에 업로드
- 날짜 범위 지정 가능
- 리포트 타입 필터링 (daily, screener, all)
- 진행 상황 표시 및 에러 핸들링

**요구사항:**
- `NOTION_TOKEN`, `NOTION_DATABASE_ID` 필요 ([설정 가이드](../README_NOTION.md))

**사용법:**
```bash
uv run jarvis report upload [시작날짜] [종료날짜] [OPTIONS]
```

**옵션:**
- `--type, -t`: 리포트 타입 (`all`, `daily`, `screener`, 기본값: all)

**예시:**
```bash
# 전체 리포트 업로드
uv run jarvis report upload

# 특정 날짜만
uv run jarvis report upload 2026-04-22

# 날짜 범위 지정
uv run jarvis report upload 2026-04-17 2026-04-22

# Daily 리포트만
uv run jarvis report upload --type daily

# Screener 리포트만 (특정 날짜)
uv run jarvis report upload 2026-04-18 --type screener
```

**출력 내용:**
```bash
3개 리포트를 Notion에 업로드합니다...

✓ daily_2026-04-22.md → https://notion.so/...
✓ screen-2026-04-18.md → https://notion.so/...
✗ daily_2026-04-21.md 실패: Duplicate entry

완료: 성공 2, 실패 1
```

---

#### 3-5. V2 튜닝/DB 확인 스크립트

**Prompt 튜닝 (실데이터 샘플 기반):**
```bash
uv run python scripts/stock_report_prompt_tuning.py 2026-05-19 \
  --model gpt-5.4-mini \
  --sample-size 30 \
  --per-channel 2 \
  --pick hana_us_stock:9609 \
  --pick shinhanresearch:50725
```

**핵심 옵션:**
- `--model`: 실험용 모델 override (config.yaml 기본값 대신 적용). 단독으로 쓸 수 있으며, 이 경우 provider는 config 기본값을 유지. `--provider`는 `--model`을 함께 지정할 때만 유효.
- `--pick`: 특정 메시지 강제 포함 (`channel_key:channel_message_id`, 반복 가능)
- `--pick-file`: selector 파일로 일괄 지정
- `--include-grouped-only`: grouped_only 후보도 샘플에 포함
- `--max-raw-chars`: 샘플 원문 길이 제한 (`<=0`이면 full)

**DB 적재 결과 확인 (knowledge_chunks):**
```bash
uv run python scripts/stock_report_show_chunks.py 2026-05-19

# 채널 필터
uv run python scripts/stock_report_show_chunks.py 2026-05-19 --channel-key hana_us_stock

# T09 입력 근거 검토용 MD 저장 (전체 evidence/supporting_facts 출력)
uv run python scripts/stock_report_show_chunks.py 2026-05-19 \
  --source-type telegram_unit_v2 \
  --output reports/2026-05/t09_input_evidence_2026-05-19.md
```

`stock_report_show_chunks.py` 출력은 `message(source_pk)` 단위로 묶어서
`canonical_summary`, `category/theme`, `evidence_items`, `qa_warnings`를 함께 보여줍니다.
각 summary에는 `chunk_ref: <channel_key>+<chunk_id>`가 포함되며,
`evidence_items`/`supporting_facts`는 잘리지 않고 전체가 출력됩니다.

**리포트 평가 (coverage + 골든 must-have 체크):**
```bash
uv run python scripts/stock_report_eval.py 2026-06-02 \
  --markdown reports/2026-06/daily_v2_2026-06-02.md \
  --golden
```

**핵심 옵션:**
- `--markdown`: 평가할 리포트 MD (생략 시 DB `report_evidence` 기준으로 coverage 계산)
- `--golden`: `tests/fixtures/stock_report/golden/<날짜>.json`의 고임팩트 must-have
  이벤트(M&A·자본조달)가 리포트에 모두 등장하는지 검사 (누락 시 종료코드 1)
- `--json`: 표 대신 JSON 출력

골든 must-have의 헤르메틱 회귀(DB·LLM 불필요)는 일반 테스트 루프에서 실행됩니다:
```bash
uv run pytest tests/pipelines/stock_report/test_golden_set.py
```

---

### 4. brief - 일일 포트 액션 브리핑

**특징:**
- `playbook.yaml`의 보유 종목과 워치리스트를 함께 평가
- 청산, 매수 가능, 축소, 진입 임박, 관망 후보 순으로 우선순위 정렬
- 뉴스·공시·수급은 점수에 반영하지 않고 근거로만 표시
- LLM 문장화 실패 또는 `--no-llm` 사용 시 규칙 원문으로 출력

**요구사항:**
- `playbook.yaml` 필요
- LLM 문장화를 쓰려면 `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` 필요
- 한국주식 실시간 가격·수급은 `KIS_APP_KEY`, `KIS_APP_SECRET` 설정 시 사용

**사용법:**
```bash
uv run jarvis brief                # LLM 문장화 포함
uv run jarvis brief --no-llm       # 규칙 원문만 (LLM 키 불필요)
```

**playbook.yaml 예시:**
```yaml
holdings:
  - ticker: "005930"
    quantity: 10
    avg_price: 72000
    stop_price: 65000   # 선택
watchlist:
  - ticker: NVDA
    note: "AI 반도체 대장"   # 선택
```

**출력 내용:**
- 시장 환경 요약
- 액션 큐 Top N
- 보유 종목의 exit verdict와 stop 근접 마커
- 워치리스트의 매수 가능 또는 진입 임박 조건
- 종목별 뉴스·공시·수급 근거
- 저장 파일: `reports/YYYY-MM/brief_YYYY-MM-DD.md`

---

### 5. screen - 시장 스크리너

**특징:**
- Naver 테마 + KIS 순위 기반 유니버스 구성
- 누적/상승일/거래량 폭발 지표 스코어링
- 후보 종목 랭킹 및 리포트 저장

**사용법:**
```bash
uv run jarvis screen [OPTIONS]
```

**옵션:**
- `--market, -m`: `kr`, `us`, `all` (기본값: all)
- `--notion`: Notion에 업로드

**예시:**
```bash
# MD 파일만 저장 (기본)
uv run jarvis screen

# 시장별 스크리닝
uv run jarvis screen --market kr
uv run jarvis screen --market us

# Notion에도 업로드
uv run jarvis screen --notion
```

---

### 6. cache - 티커 캐시 관리

종목명→티커 심볼 변환 결과를 로컬에 캐시합니다 (6개월 TTL).

```bash
uv run jarvis cache list      # 캐시된 매핑 목록
uv run jarvis cache clear     # 캐시 초기화 (확인 프롬프트)
uv run jarvis cache clear --yes  # 확인 없이 초기화
```

---

### 7. telegram - 텔레그램 채널 수집

**특징:**
- Telethon 기반 채널 메시지 수집
- include/exclude 정규식 필터링
- **채널별 timezone 설정 지원** (KST, UTC 등)
- 날짜별 CSV 저장 (중복 방지)
- catch-up 모드로 누락분 자동 보충
- **사진/PDF 자동 다운로드** (첨부파일 + URL)

**요구사항:**
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` 필요
- `config.yaml`에 `telegram.channels` 설정 필요
- 첫 실행 시 Telegram 인증 (전화번호/코드) 필요

**사용법:**
```bash
# 전날 메시지 수집 (기본)
uv run jarvis telegram fetch

# 특정 날짜 수집 (채널 timezone 기준)
uv run jarvis telegram fetch 2026-04-12

# 누락분 보충 수집
uv run jarvis telegram catch-up

# 커스텀 설정 파일
uv run jarvis telegram fetch --config my_config.yaml
```

**데이터 저장:**
- CSV: `data/YYYY-MM/YYYY-MM-DD-{channel_id}.csv` (채널 timezone 기준)
- 사진: `data/images/YYYY-MM-DD/{channel_id}_{msg_id}.jpg`
- 첨부 PDF: `data/files/YYYY-MM-DD/{channel_id}_{msg_id}_{filename}.pdf`
- URL PDF: `data/files/YYYY-MM-DD/{channel_id}_url_{msg_id}_{filename}.pdf`
- 상태: `data/monitor_state.json`

**파일명 규칙:** `channel_id`는 `config.yaml`에 설정한 영문 ID (예: "shinhanresearch")를 사용합니다.

---

### 첫 실행 가이드

#### 1. Telegram API 자격증명 발급

1. https://my.telegram.org/apps 접속
2. 로그인 후 "Create application" 클릭
3. `api_id`와 `api_hash`를 `.env`에 추가:

```bash
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
```

#### 2. 첫 실행 (인증)

**최초 1회만 필요**합니다:

```bash
$ uv run jarvis telegram fetch

Please enter your phone (or bot token): +821012345678  # 국가코드 포함
Please enter the code you received: 12345              # Telegram 앱에서 수신한 코드
```

인증 완료 후 `anon.session` 파일이 생성되며, **다음부터는 자동 로그인**됩니다.

#### 3. 채널 설정

`config.yaml`의 `telegram.channels`에 수집할 채널 추가:

```yaml
telegram:
  channels:
    - "channel_username"      # 간단한 형식 (timezone: UTC)
    
    - id: "korean_channel"    # 한국 채널 (KST)
      timezone: "Asia/Seoul"
    
    - id: "filtered_channel"  # 필터 + timezone
      timezone: "Asia/Seoul"
      include:
        - "Breaking|Urgent"   # 정규식
      exclude:
        - "(?i)ad|광고"
  output_dir: "data"
```

**중요: Timezone 설정**

메시지 timestamp는 UTC로 제공되지만, 채널 운영자는 보통 현지 시간대를 사용합니다.  
`timezone` 설정으로 메시지를 올바른 날짜에 저장할 수 있습니다.

**예시:**
- UTC 2026-04-08 23:14 발송 메시지
- `timezone: "Asia/Seoul"` 설정 시 → KST 2026-04-09 08:14
- **2026-04-09** 폴더에 저장 ✅

**지원 timezone:** [IANA Timezone Database](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)  
(예: `Asia/Seoul`, `America/New_York`, `Europe/London`, `UTC`)

---

### 문제 해결

**Q: 전화번호 입력 후 "Phone number invalid" 에러**  
A: 국가코드를 포함하세요 (한국: `+82`, 미국: `+1`)

**Q: 세션 파일 위치 변경?**  
A: `.env`에 `TELETHON_SESSION_NAME=my_session` 추가

**Q: 채널 ID를 모르겠어요**  
A: Telegram 앱에서 채널 정보 → "ID" 확인, 또는 `@channel_username` 사용

**Q: 비공개 채널이 수집 안 됨**  
A: 해당 Telegram 계정이 채널 멤버여야 수집 가능합니다

---

## LLM 모델 설정

LLM 모델·provider·temperature는 `config.yaml`의 `llm:` 섹션에서 일괄 관리한다.
CLI에 `--provider` 플래그는 없으며 (실험용 스크립트 제외), 모델 변경은 설정 파일만 수정하면 된다.

### config.yaml 스키마

```yaml
llm:
  defaults:
    provider: openai
    model: gpt-5.6-terra
    temperature: 0.0
  daily:                 # jarvis report daily (MapReduce 파이프라인)
    map:     { model: gpt-5.6-luna, temperature: 0.2 }
    shuffle: { model: gpt-5.6-luna, temperature: 0.1 }
    reduce:  { temperature: 0.3 }   # model은 defaults.model 상속
    wrapup:  { temperature: 0.4 }
  daily_v2:              # jarvis report daily-v2
    extraction: { model: gpt-5.6-luna, temperature: 0.1 }
    synthesis:  { model: gpt-5.6-sol,  temperature: 0.1 }
  analyze: {}            # jarvis analyze → defaults 전부 상속
  brief:   {}            # jarvis brief → defaults 전부 상속
```

**상속 규칙**: 각 항목은 `defaults`를 기반으로 명시한 필드만 덮어쓴다.
`llm:` 섹션 자체가 없어도 위 스키마와 동일한 코드 기본값이 적용되므로 설정 파일 없이도 동작한다.

> **참고**: llm 섹션은 루트 config.yaml에서만 읽는다 (`--config-path`는 normalize 전용).

---

## 환경 변수 설정

### LLM API 키 (.env)
```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1  # 선택

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_BASE_URL=https://api.anthropic.com  # 선택
```

### KIS API 키 (.env)
```bash
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_ACCOUNT_NO=...
```

### Stock Report V2 DB (.env)
```bash
# 둘 중 하나 사용
STOCK_REPORT_DB_DSN=postgresql://report:${DB_PASSWORD}@localhost:5432/stock_report
DATABASE_URL=postgresql://report:${DB_PASSWORD}@localhost:5432/stock_report
```

---

## 문제 해결

### "ModuleNotFoundError" 에러
```bash
# 의존성 재설치
uv sync --all-extras
uv pip install -e .
```

### jarvis 명령어를 찾을 수 없음
```bash
# uv run 사용
uv run jarvis --help

# 또는 alias 추가 (위 방법 2 참조)
```

### API 키 에러
```bash
# .env 파일 확인
cat .env

# 환경 변수 확인
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY
```

### 가격 데이터가 이상함 (nan, 0 등)
- yfinance API 일시적 장애일 수 있음
- 잠시 후 재시도
- 티커 심볼이 올바른지 확인

---

## 팁

### 1. 빠른 체크부터 시작
```bash
# 먼저 check로 빠르게 확인
uv run jarvis check AAPL

# 관심 있으면 analyze로 심층 분석
uv run jarvis analyze AAPL
```

### 2. 여러 종목 동시 분석
```bash
# check로 한 번에 여러 종목 기술 체크 (LLM 없이)
uv run jarvis check AAPL MSFT GOOGL AMZN META
```

### 3. 정기적인 모니터링
```bash
# cron이나 스케줄러로 자동화
0 9 * * 1-5 cd /path/to/invest-jarvis && uv run jarvis check AAPL MSFT NVDA
```

### 4. 출력 저장
```bash
# 파일로 저장
uv run jarvis check AAPL > aapl_analysis.txt

# 날짜별로 저장
uv run jarvis report daily-v2 2026-05-19 > report_v2_$(date +%Y%m%d).txt
```


---

## NH 계좌와 매매일지

`.env`에 `NS_APP_KEY`, `NS_APP_SECRET`을 설정한다. 토큰은 사용자 cache(`~/.cache/invest-jarvis/nhplug`)에서 AppKey별로 재사용한다. 원문 계좌번호 대신 `broker accounts`에 표시되는 `nh-...` 식별자를 사용한다. 개인 실계좌가 여러 개면 `--account`가 필수이며 모의·주문대리인 계좌는 자동 선택하지 않는다.

```bash
uv run jarvis broker accounts
uv run jarvis broker holdings --account nh-계좌식별자
uv run jarvis brief --broker nh --account nh-계좌식별자 --no-llm
```

다른 worktree의 기존 `.env`를 읽으려면 `uv run --env-file /absolute/path/.env jarvis ...`를 사용한다. 키 값을 명령 인자로 직접 전달하지 않는다. 사용자 손절 기준과 관심 종목을 재사용하려면 해당 worktree의 로컬 `playbook.yaml`을 준비한다. NH 조회로 이 파일을 수정하지 않는다.

잔고는 두 시장을 모두 조회한 후 표시한다. 한 시장이 실패하면 전체 조회를 실패로 처리하며 YAML 보유로 대체하지 않는다. NH 평가 기준가와 차트 분석 가격은 출처·시점이 다르다. 조회 시각은 가격 거래일을 뜻하지 않으며, 국내·해외 총자산과 KRW/USD 금액을 합산하지 않는다. NH 소수점 보유는 그대로 표시하고 기존 정수 기준 수량 계획만 생략한다.

국내 전체 잔고에 포함된 RP 등 주식 코드 형식을 지원하지 않는 자산은 브리핑의 `주식 분석 제외 자산`에 표시한다. 잔고와 출처 합계는 유지하며 주식 시세·전략 분석에는 전달하지 않는다. 이 자산의 수량 단위는 NH 제공 기준이다.

브리프 Markdown은 `# 일일 브리프 → ## 보유/워치리스트 → ### 종목 → #### 분석 항목` 순서다. 분석 안의 세부 제목은 한 단계 더 내려가며, 후속 참고 정보는 별도 `####`로 구분한다.

### 거래 수집과 조회

```bash
uv run jarvis trades sync --account nh-계좌식별자 --from 2026-08-06 --to 2026-11-06
uv run jarvis trades list
uv run jarvis trades list --detail
uv run jarvis trades list --ticker AAPL --market US --not-reviewed
uv run jarvis trades list --from 2026-11-01 --to 2026-11-30 --tag 돌파
uv run jarvis trades show nh-case-투자건식별자
```

기간은 양 끝 날짜를 포함한다. 국내는 주문일 기준 누적 체결만 수집하고, 미국은 조회 장부일 기준 일별 거래내역에서 실제 매매를 수집하므로 최근 체결의 반영 지연이 있을 수 있다. 미국 실거래일은 제공된 경우 별도로 표시한다. 전체 수집이 성공한 뒤 한 번에 장부에 반영하며, 재수집은 같은 거래를 중복 추가하지 않는다.

위 수집 예시는 3개월 범위다. `list`와 `export`는 기본적으로 월별 매수·매도 금액, 투자 건 요약, 작성한 메모만 표시한다. 금액은 계좌·시장·통화별로 구분하며 실현손익을 계산하지 않는다. 기간 필터는 투자 건을 선택하므로 요약에는 선택한 투자 건의 전체 거래 이력이 포함된다. 계좌 전체의 월별 합계로 해석하지 않는다. 거래 ID·수수료 원문·개별 확인사항은 `--detail`로 확인한다. `show`는 단일 투자 건의 상세를 표시한다.

투자 건은 계좌·시장·통화·종목·신용/대출 구분별 장부를 기준으로 묶는다. 날짜 단위 자료로 같은 날 체결 순서를 단정하지 않으며, 이력 시작 전 보유를 알 수 없는 매도는 불완전으로 표시한다. 미국 거래의 시작 잔고가 양수이거나 거래 전·후 잔고와 수집한 매매가 맞지 않아도 불완전으로 표시하고 잔여 수량을 확정하지 않는다. 표시된 source 잔고는 해당 거래 당시 값이다. 장부상 수량/청산은 실계좌 전체 이력을 증명하지 않는다.

### 이유·계획·복기 기록

```bash
uv run jarvis trades note nh-case-투자건식별자 --reason '돌파 후 거래량 유지' --invalidation '돌파선 종가 이탈' --add-condition '눌림목 지지 확인' --strategy '돌파' --tag 돌파
uv run jarvis trades note nh-case-투자건식별자 --review '진입 기준은 지켰으나 비중 확대가 빨랐음'
uv run jarvis trades note nh-case-투자건식별자 --source-link reports/entry-analysis.md --provenance saved_at_trade
uv run jarvis trades note nh-case-투자건식별자 --source-link reports/recomputed-analysis.md --provenance retrospective
uv run jarvis trades split nh-trade-거래식별자 --title '별도 전략' --strategy '눌림목'
```

지정하지 않은 메모 필드는 보존한다. 텍스트 필드는 빈 문자열을 명시하면 지운다. `--tag`와 `--source-link`는 반복 지정할 수 있으며 지정하면 해당 목록을 교체한다. 링크는 기록만 하고 자동 접속하거나 과거 분석을 재생성하지 않는다. 수동 분리 경계는 거래일과 안정적인 표시순 기준이며 같은 날 실제 체결 순서를 뜻하지 않는다.

### 로컬 내보내기와 저장

```bash
uv run jarvis trades export --month 2026-11 --output reports/trades-2026-11.md
uv run jarvis trades export --detail --output reports/trades-detail.md
uv run jarvis trades export --case nh-case-투자건식별자
uv run jarvis trades list --db data/broker/another-journal.sqlite3
```

기본 장부는 `data/broker/trades.sqlite3`이며 모든 `trades` 명령에서 `--db`로 바꿀 수 있다. 자동 거래 사실과 사용자 메모를 분리 저장한다. 내보내기는 새 경로에만 파일을 생성하고 기존 파일·장부·symlink를 덮어쓰지 않는다. 기존 notebook과 Notion에는 자동 전송하지 않는다. 거래 수집·장부 충돌·조회 실패는 종료코드 1이며 메모와 기존 사실은 보존한다.
