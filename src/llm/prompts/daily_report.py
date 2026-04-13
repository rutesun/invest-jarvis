# src/llm/prompts/daily_report.py
from __future__ import annotations


class DailyReportPrompts:
    @staticmethod
    def map_issues(known_themes: str, messages: str) -> str:
        """Stage 2: 텔레그램 메시지에서 테마/종목/감성 추출"""
        return f"""아래 텔레그램 메시지들에서 투자 관련 이슈를 추출하세요.
각 이슈에 대해:
- theme: 투자 테마명. 아래 기존 테마 목록에 해당하면 그대로 사용하고,
         해당하지 않으면 새 테마명을 자유 생성하세요.
- tickers: 언급된 종목명 (원문 그대로, 정규화하지 않음)
- sentiment: 시장 영향 방향 (bull/bear/neutral)
- summary: 핵심 내용 요약
- source_ids: 해당 메시지 ID 목록

기존 테마 목록:
{known_themes}

잡담, 광고, 투자와 무관한 메시지는 무시하세요.
한 메시지가 여러 테마를 다루면 각각 별도로 분리하세요.

메시지:
{messages}"""

    @staticmethod
    def merge_themes(known_themes: str, new_themes: str) -> str:
        """Stage 3 Step 1: 유사 테마 병합"""
        return f"""아래에 기존 테마 목록과 새로 추출된 테마 목록이 있습니다.
새 테마 중 기존 테마와 동일하거나 유사한 것은 기존 테마명으로 매핑하고,
완전히 새로운 테마는 그대로 유지하세요.

기존 테마 목록:
{known_themes}

새로 추출된 테마:
{new_themes}

출력: {{"매핑": {{"원래 테마명": "정규화된 테마명", ...}}}}"""

    @staticmethod
    def catalyst(themes_json: str) -> str:
        """Stage 4: 주도주별 촉매 뉴스 검색"""
        return f"""아래 테마별 주도주 목록이 주어집니다.
각 종목에 대해 NewsTool로 최근 뉴스를 검색하고,
해당 종목이 주목받는 촉매(catalyst)를 파악하세요.

테마당 상위 2-3개 종목에 집중하세요.
뉴스가 없는 종목은 텔레그램 원문 요약을 촉매로 사용하세요.

테마 및 주도주:
{themes_json}"""

    @staticmethod
    def synthesize(macro: str, news: str, themes: str, catalysts: str) -> str:
        """Stage 5: 전체 통합 리포트 생성"""
        return f"""아래 데이터를 기반으로 일일 시장 리포트의 총평 및 인사이트를 작성하세요.

작성할 섹션:
1. 시장 온도 (Market Pulse): 매크로 수치 해석과 뉴스 흐름을 바탕으로 한 종합적인 시장 심리 및 분위기 판단 (5~10줄)
2. 주요 인사이트 (Featured Analysis): 오늘의 발견된 테마와 촉매(뉴스), 특징주들을 엮어서 시장을 관통하는 핵심 시사점, 트렌드 이동, 리스크 요인 등을 전문적이고 입체적으로 분석 (1~2단락)

매크로:
{macro}

시장 뉴스:
{news}

테마 분석:
{themes}

촉매 분석:
{catalysts}"""
