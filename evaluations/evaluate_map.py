"""Map stage 평가 스크립트.

Usage:
    uv run python evaluations/evaluate_map.py
    uv run python evaluations/evaluate_map.py --prompt-version v2_test
    uv run python evaluations/evaluate_map.py --llm-judge  # LLM-as-Judge 활성화
"""

import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from src.pipelines.daily_report.models import TelegramMessage, MappedIssue
from src.pipelines.daily_report.stages.map_stage import map_stage
from evaluations.metrics import evaluate_all, RULE_BASED_METRICS


def load_test_cases(path: str = "evaluations/datasets/test_cases.json") -> List[Dict]:
    """테스트 케이스 로드."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["test_cases"]


def create_telegram_message(text: str, case_id: str) -> TelegramMessage:
    """테스트용 TelegramMessage 생성."""
    return TelegramMessage(
        channel_id="test",
        message_id=case_id,
        timestamp=datetime.now(),
        text=text,
    )


def run_evaluation(
    test_cases: List[Dict],
    prompt_version: str = "current",
    use_llm_judge: bool = False,
) -> Dict[str, Any]:
    """전체 테스트 케이스에 대해 평가 실행."""
    results = {
        "prompt_version": prompt_version,
        "timestamp": datetime.now().isoformat(),
        "use_llm_judge": use_llm_judge,
        "cases": [],
        "summary": {},
    }

    # LLM 인스턴스 (LLM-as-Judge용, 재사용)
    llm = None
    if use_llm_judge:
        from src.llm.provider import LLMProvider
        llm = LLMProvider.create(
            provider="anthropic",
            model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            temperature=0,
        )
        print("🤖 LLM-as-Judge 활성화")

    all_scores = {name: [] for name in RULE_BASED_METRICS.keys()}

    for case in test_cases:
        case_id = case["id"]
        case_name = case["name"]
        input_text = case["input"]
        expected = case["expected"]

        print(f"\n{'='*60}")
        print(f"📋 {case_id}: {case_name}")
        print(f"{'='*60}")
        suffix = "..." if len(input_text) > 80 else ""
        print(f"Input: {input_text[:80]}{suffix}")

        # TelegramMessage로 변환
        message = create_telegram_message(input_text, case_id)

        # Map stage 실행
        try:
            issues = map_stage([message])
        except Exception as e:
            print(f"❌ Error: {e}")
            issues = []

        # 결과 출력
        print(f"\n📊 Output: {len(issues)} issues")
        for i, issue in enumerate(issues):
            print(f"  [{i+1}] {issue.title}")
            print(f"      themes: {issue.themes}")
            print(f"      keywords: {issue.keywords[:5]}...")

        # 메트릭 계산
        metrics = evaluate_all(issues, expected, use_llm_judge=use_llm_judge, llm=llm)

        # 점수 수집 (숫자만)
        for name, value in metrics.items():
            if isinstance(value, (int, float)) and name in all_scores:
                all_scores[name].append(value)

        # Pass/Fail 판정 (숫자 메트릭만)
        numeric_scores = [v for v in metrics.values() if isinstance(v, (int, float))]
        passed = all(score >= 0.8 for score in numeric_scores)
        status = "✅ PASS" if passed else "❌ FAIL"

        print(f"\n{status}")
        for name, value in metrics.items():
            if isinstance(value, (int, float)):
                emoji = "✓" if value >= 0.8 else "✗"
                print(f"  {emoji} {name}: {value:.2f}")
            elif name == "theme_relevance_details" and value:
                print(f"  📝 LLM Judge 상세:")
                for detail in value:
                    match_icon = "✓" if detail.get("matched") else "✗"
                    print(f"     {match_icon} {detail.get('expected')} → {detail.get('reason', 'N/A')}")

        # 결과 저장 (JSON 직렬화 가능하도록)
        serializable_metrics = {
            k: v for k, v in metrics.items()
            if isinstance(v, (int, float, str, bool, list))
        }
        case_result = {
            "id": case_id,
            "name": case_name,
            "passed": passed,
            "metrics": serializable_metrics,
            "output": [issue.model_dump() for issue in issues],
        }
        results["cases"].append(case_result)

    # 전체 요약
    results["summary"] = {
        name: sum(scores) / len(scores) if scores else 0.0
        for name, scores in all_scores.items()
    }

    return results


def save_results(results: Dict, output_dir: str = "evaluations/results"):
    """결과를 JSON 파일로 저장."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    version = results["prompt_version"]
    filename = f"{timestamp}_{version}.json"
    filepath = Path(output_dir) / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Results saved: {filepath}")
    return filepath


def print_summary(results: Dict):
    """전체 요약 출력."""
    summary = results["summary"]
    cases = results["cases"]

    passed_count = sum(1 for c in cases if c["passed"])
    total_count = len(cases)

    print(f"\n{'='*60}")
    print(f"📈 EVALUATION SUMMARY ({results['prompt_version']})")
    print(f"{'='*60}")
    print(f"Cases: {passed_count}/{total_count} passed ({passed_count/total_count*100:.0f}%)")
    print()
    print("Average Scores:")
    for name, score in summary.items():
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        print(f"  {name:25} {bar} {score:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Map stage 평가")
    parser.add_argument(
        "--prompt-version",
        default="current",
        help="프롬프트 버전 이름 (결과 파일명용)",
    )
    parser.add_argument(
        "--test-cases",
        default="evaluations/datasets/test_cases.json",
        help="테스트 케이스 파일 경로",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="결과 파일 저장 안함",
    )
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="LLM-as-Judge로 테마 평가 (더 정확하지만 느림)",
    )
    args = parser.parse_args()

    print("🚀 Map Stage Evaluation")
    print(f"   Prompt version: {args.prompt_version}")
    print(f"   Test cases: {args.test_cases}")
    print(f"   LLM-as-Judge: {'ON' if args.llm_judge else 'OFF'}")

    # 테스트 케이스 로드
    test_cases = load_test_cases(args.test_cases)
    print(f"   Loaded {len(test_cases)} test cases")

    # 평가 실행
    results = run_evaluation(test_cases, args.prompt_version, args.llm_judge)

    # 요약 출력
    print_summary(results)

    # 결과 저장
    if not args.no_save:
        save_results(results)


if __name__ == "__main__":
    main()
