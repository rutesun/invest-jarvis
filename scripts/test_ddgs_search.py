#!/usr/bin/env python3
"""DuckDuckGo Search 테스트 스크립트

Usage:
    # 기본 뉴스 검색
    python scripts/test_ddgs_search.py

    # 특정 키워드 검색
    python scripts/test_ddgs_search.py --keyword "삼성전자"

    # 사이트 제약
    python scripts/test_ddgs_search.py --keyword "삼성전자" --site "mk.co.kr"

    # 일반 검색 (뉴스가 아닌)
    python scripts/test_ddgs_search.py --keyword "AAPL" --type text

    # 시간 제한
    python scripts/test_ddgs_search.py --keyword "삼성전자" --timelimit d

    # IDE 디버그: 이 파일을 열고 F5 (Run and Debug)
"""

import argparse
import time
from datetime import datetime
from typing import Any

from ddgs import DDGS
from ddgs.exceptions import DDGSException


def format_datetime(date_str: str) -> str:
    """ISO 8601 날짜를 읽기 쉬운 형식으로 변환"""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return date_str


def search_news(
    keyword: str,
    site: str | None = None,
    region: str = "kr-kr",
    timelimit: str = "d",
    max_results: int = 10,
    retries: int = 3,
) -> list[dict[str, Any]]:
    """DuckDuckGo 뉴스 검색 (재시도 로직 포함)

    Args:
        keyword: 검색어
        site: 사이트 제약 (예: "mk.co.kr", "bloomberg.com")
        region: 지역 코드 ("kr-kr", "us-en", None)
        timelimit: 시간 제한 ("d", "w", "m", "y", None)
        max_results: 최대 결과 수
        retries: 재시도 횟수

    Returns:
        뉴스 기사 리스트
    """
    # site: 연산자 추가
    query = f"{keyword} site:{site}" if site else keyword

    print(f"🔍 검색 중: {query}")
    print(f"   Region: {region}, Time: {timelimit}, Max: {max_results}\n")

    for attempt in range(retries):
        try:
            ddgs = DDGS()
            results = ddgs.news(
                query,
                region=region,
                timelimit=timelimit,
                max_results=max_results,
            )
            return list(results)
        except DDGSException as e:
            print(f"⚠️  시도 {attempt + 1}/{retries} 실패: {e}")
            if attempt < retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"   {wait_time}초 후 재시도...\n")
                time.sleep(wait_time)
            else:
                print(f"❌ {retries}회 시도 후 실패\n")
                raise
        except Exception as e:
            print(f"❌ 예상치 못한 에러: {e}\n")
            raise

    return []


def search_text(
    keyword: str,
    site: str | None = None,
    region: str = "kr-kr",
    timelimit: str | None = None,
    max_results: int = 10,
    retries: int = 3,
) -> list[dict[str, Any]]:
    """DuckDuckGo 일반 웹 검색 (재시도 로직 포함)

    Args:
        keyword: 검색어
        site: 사이트 제약
        region: 지역 코드
        timelimit: 시간 제한
        max_results: 최대 결과 수
        retries: 재시도 횟수

    Returns:
        검색 결과 리스트
    """
    # site: 연산자 추가
    query = f"{keyword} site:{site}" if site else keyword

    print(f"🔍 검색 중: {query}")
    print(f"   Region: {region}, Time: {timelimit}, Max: {max_results}\n")

    for attempt in range(retries):
        try:
            ddgs = DDGS()
            results = ddgs.text(
                query,
                region=region,
                timelimit=timelimit,
                max_results=max_results,
            )
            return list(results)
        except DDGSException as e:
            print(f"⚠️  시도 {attempt + 1}/{retries} 실패: {e}")
            if attempt < retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"   {wait_time}초 후 재시도...\n")
                time.sleep(wait_time)
            else:
                print(f"❌ {retries}회 시도 후 실패\n")
                raise
        except Exception as e:
            print(f"❌ 예상치 못한 에러: {e}\n")
            raise

    return []


def search_multiple_sites(
    keyword: str,
    sites: list[str],
    search_type: str = "news",
    timelimit: str = "d",
    max_results: int = 20,
    retries: int = 3,
) -> list[dict[str, Any]]:
    """여러 사이트에서 OR 검색 (재시도 로직 포함)

    Args:
        keyword: 검색어
        sites: 사이트 리스트 (예: ["mk.co.kr", "hankyung.com"])
        search_type: "news" 또는 "text"
        timelimit: 시간 제한
        max_results: 최대 결과 수
        retries: 재시도 횟수

    Returns:
        검색 결과 리스트
    """
    site_query = " OR ".join(f"site:{s}" for s in sites)
    query = f"{keyword} ({site_query})"

    print(f"🔍 다중 사이트 검색: {query}")
    print(f"   Type: {search_type}, Time: {timelimit}, Max: {max_results}\n")

    for attempt in range(retries):
        try:
            ddgs = DDGS()
            if search_type == "news":
                results = ddgs.news(
                    query,
                    region="kr-kr",
                    timelimit=timelimit,
                    max_results=max_results,
                )
            else:
                results = ddgs.text(
                    query,
                    region="kr-kr",
                    timelimit=timelimit,
                    max_results=max_results,
                )
            return list(results)
        except DDGSException as e:
            print(f"⚠️  시도 {attempt + 1}/{retries} 실패: {e}")
            if attempt < retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"   {wait_time}초 후 재시도...\n")
                time.sleep(wait_time)
            else:
                print(f"❌ {retries}회 시도 후 실패\n")
                raise
        except Exception as e:
            print(f"❌ 예상치 못한 에러: {e}\n")
            raise

    return []


def print_news_results(results: list[dict[str, Any]]) -> None:
    """뉴스 검색 결과 출력"""
    if not results:
        print("❌ 검색 결과가 없습니다.\n")
        return

    print(f"✅ {len(results)}건의 뉴스 발견\n")
    print("=" * 80)

    for i, article in enumerate(results, 1):
        date = format_datetime(article.get("date", ""))
        source = article.get("source", "Unknown")
        title = article.get("title", "No title")
        url = article.get("url", "")
        body = article.get("body", "")[:150]

        print(f"\n[{i}] {title}")
        print(f"    📅 {date} | 📰 {source}")
        print(f"    🔗 {url}")
        if body:
            print(f"    💬 {body}...")

    print("\n" + "=" * 80)


def print_text_results(results: list[dict[str, Any]]) -> None:
    """일반 검색 결과 출력"""
    if not results:
        print("❌ 검색 결과가 없습니다.\n")
        return

    print(f"✅ {len(results)}건의 결과 발견\n")
    print("=" * 80)

    for i, item in enumerate(results, 1):
        title = item.get("title", "No title")
        url = item.get("href", "")
        body = item.get("body", "")[:150]

        print(f"\n[{i}] {title}")
        print(f"    🔗 {url}")
        if body:
            print(f"    💬 {body}...")

    print("\n" + "=" * 80)


def run_interactive_examples():
    """대화형 예제 모음 (IDE 디버그용)

    이 함수를 직접 수정해서 테스트하세요.
    브레이크포인트를 여기 아래에 걸고 F5로 디버그하면 됩니다.
    """
    print("🎯 DuckDuckGo Search 테스트\n")

    # ============================================================
    # 여기를 자유롭게 수정해서 테스트하세요!
    # ============================================================

    # 예제: 삼성전자 뉴스 검색
    results = search_news("삼성전자", region="kr-kr", timelimit="d", max_results=5)
    print_news_results(results)

    # 예제: 특정 사이트에서 검색
    # results = search_news("삼성전자", site="mk.co.kr", max_results=5)
    # print_news_results(results)

    # 예제: 여러 사이트에서 검색
    # sites = ["mk.co.kr", "hankyung.com", "sedaily.com"]
    # results = search_multiple_sites("삼성전자", sites, max_results=10)
    # print_news_results(results)

    # 예제: 미국 뉴스
    # results = search_news("AAPL", region="us-en", timelimit="d", max_results=5)
    # print_news_results(results)

    # 예제: 일반 웹 검색
    # results = search_text("삼성전자 리포트", site="shinhansec.com", max_results=5)
    # print_text_results(results)


def main():
    parser = argparse.ArgumentParser(
        description="DuckDuckGo Search 테스트 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 대화형 예제 실행
  python scripts/test_ddgs_search.py

  # 특정 키워드 뉴스 검색
  python scripts/test_ddgs_search.py --keyword "삼성전자"

  # 사이트 제약
  python scripts/test_ddgs_search.py --keyword "삼성전자" --site "mk.co.kr"

  # 일반 웹 검색
  python scripts/test_ddgs_search.py --keyword "삼성전자" --type text

  # 여러 사이트 검색
  python scripts/test_ddgs_search.py --keyword "삼성전자" --sites "mk.co.kr,hankyung.com"

  # 시간 제한 (d=일, w=주, m=월)
  python scripts/test_ddgs_search.py --keyword "AAPL" --timelimit w
        """,
    )

    parser.add_argument(
        "--keyword",
        "-k",
        type=str,
        help="검색 키워드",
    )
    parser.add_argument(
        "--type",
        "-t",
        type=str,
        choices=["news", "text"],
        default="news",
        help="검색 타입 (기본: news)",
    )
    parser.add_argument(
        "--site",
        "-s",
        type=str,
        help="특정 사이트로 제약 (예: mk.co.kr)",
    )
    parser.add_argument(
        "--sites",
        type=str,
        help="여러 사이트 (쉼표로 구분, 예: mk.co.kr,hankyung.com)",
    )
    parser.add_argument(
        "--region",
        "-r",
        type=str,
        default="kr-kr",
        help="지역 코드 (기본: kr-kr)",
    )
    parser.add_argument(
        "--timelimit",
        type=str,
        choices=["d", "w", "m", "y"],
        default="d",
        help="시간 제한: d(일), w(주), m(월), y(년) (기본: d)",
    )
    parser.add_argument(
        "--max-results",
        "-n",
        type=int,
        default=10,
        help="최대 결과 수 (기본: 10)",
    )

    args = parser.parse_args()

    # 키워드 없으면 대화형 예제 실행
    if not args.keyword:
        run_interactive_examples()
        return

    # 여러 사이트 검색
    if args.sites:
        sites = [s.strip() for s in args.sites.split(",")]
        results = search_multiple_sites(
            args.keyword,
            sites,
            search_type=args.type,
            timelimit=args.timelimit,
            max_results=args.max_results,
        )
    # 단일 검색
    elif args.type == "news":
        results = search_news(
            args.keyword,
            site=args.site,
            region=args.region,
            timelimit=args.timelimit,
            max_results=args.max_results,
        )
    else:
        results = search_text(
            args.keyword,
            site=args.site,
            region=args.region,
            timelimit=args.timelimit if args.timelimit != "d" else None,
            max_results=args.max_results,
        )

    # 결과 출력
    if args.type == "news":
        print_news_results(results)
    else:
        print_text_results(results)


if __name__ == "__main__":
    # IDE 디버그 시 여기에 브레이크포인트 설정 가능
    main()
