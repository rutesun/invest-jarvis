---
name: jarvis-notebook
description: Record and manage investment journal entries (trades, thoughts, research) in Obsidian-compatible markdown
---

# Investment Notebook

투자 기록을 Obsidian 볼트(`notebook/`)에 저장하는 보조 스킬.
사용자가 기록을 요청하면 이 규칙에 따라 해당 파일에 **append** 한다.

## 볼트 구조

```
notebook/
├── trades/YYYY-MM.md      # 매매일지
├── thoughts/YYYY-MM.md    # 시장 단상
└── research/YYYY-MM.md    # 기사·리포트 링크 + 분석
```

파일이 없으면 frontmatter와 H1 제목을 포함해 새로 생성한다.

## 파일 frontmatter (신규 파일 생성 시)

```markdown
---
type: trades | thoughts | research
month: YYYY-MM
tags: [매매일지 | 시장단상 | 리서치]
---

# 매매일지 YYYY-MM   (또는 시장 단상 / 리서치)
```

## 항목 구조

```markdown
## YYYY-MM-DD          ← 날짜 헤더 (H2), 해당 날짜 첫 항목일 때만 추가

### 항목 제목          ← 항목 헤더 (H3)
- **태그**: #티커 #테마 #액션
- **출처**: [제목](URL)    ← research에만
```

- 항목은 작고 자기완결적으로. 그 섹션만 읽어도 종목·이유·날짜가 드러나야 한다.
- 같은 날짜의 H2 헤더가 이미 있으면 중복 추가하지 않는다.

## 타입별 필드

### trades (매매일지)
```markdown
### {종목명} {매수|매도}
- **액션**: #매수 | #매도
- **태그**: #티커 #테마
- **이유**:
    - (기술적·펀더멘털 근거)
- **진입가/비중**: (기록)
- **리스크**: (예상 리스크)
- **결과/회고**: (사후 기록, 빈 칸으로 남겨도 됨)
```

### thoughts (시장 단상)
```markdown
### {단상 제목}
- **태그**: #테마 #지표 #인물
- (자유 서술, 불릿 권장)
- **연결**: [[thoughts/YYYY-MM#{관련 항목}]]
```

### research (기사·리포트)
```markdown
### {제목} — {핵심 키워드}
- **태그**: #티커 #테마
- **출처**: [기사 제목](URL) (YYYY-MM-DD)

> [!quote] 원본 발췌
> (원문 그대로 인용)

> [!note] 내 분석
> - (내 해석, 판단)

> [!warning] 리스크        ← 선택
> (리스크 요인)

> [!info] 추가 확인 포인트  ← 선택
> (후속 체크 항목)

- **연결**: [[thoughts/YYYY-MM#{관련 단상}]]
```

## 콜아웃 타입 규칙

| 타입 | 용도 |
|------|------|
| `[!quote]` | 원본 발췌 (객관 사실) |
| `[!note]` | 내 분석·판단 (주관) |
| `[!warning]` | 리스크·주의 사항 |
| `[!info]` | 추가 확인 포인트 |

## 태그 규칙

- 종목: `#삼성전자` `#하이닉스` `#NVDA` (한글명 또는 영문 티커)
- 테마: `#반도체` `#AI서버` `#MLCC` `#금리`
- 액션: `#매수` `#매도` `#관망`
- 기타: `#시장구조` `#리스크관리` `#실적` 등 자유

## 위키링크 연결

- 같은 파일 내: `[[YYYY-MM#{항목 제목}]]`
- 다른 폴더: `[[research/YYYY-MM#{항목 제목}]]`
- 아직 없는 항목도 미리 링크 가능

## 작업 방식

1. 사용자가 기록할 내용을 주면 → 타입(trades/thoughts/research) 판단
2. `notebook/{type}/YYYY-MM.md` 읽기 (없으면 신규 생성)
3. 해당 날짜 H2가 있으면 그 아래, 없으면 날짜 H2 추가 후 항목 append
4. 관련 항목이 다른 파일에 있으면 위키링크로 연결
5. 파일 변경 후 "어느 파일 어느 섹션에 추가했다"고 한 줄 보고
