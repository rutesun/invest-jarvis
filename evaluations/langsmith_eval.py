"""LangSmith 연동 Map stage 평가.

Usage:
    # 데이터셋 생성 (최초 1회)
    uv run python evaluations/langsmith_eval.py --create-dataset

    # 평가 실행
    uv run python evaluations/langsmith_eval.py --experiment v1_baseline
"""

import json
import argparse
from datetime import datetime
from typing import Dict, Any, List

from langsmith import Client, evaluate
from langsmith.schemas import Example, Run

from src.pipelines.daily_report.models import TelegramMessage, MappedIssue
from src.pipelines.daily_report.stages.map_stage import map_stage
from src.llm.provider import LLMProvider
from evaluations.metrics import (
    split_accuracy as _split_accuracy,
    number_preservation as _number_preservation,
    company_preservation as _company_preservation,
    keyword_coverage as _keyword_coverage,
    must_split_check as _must_split_check,
    _issues_to_text,
    ThemeMatchResult,
)

# LangSmith 클라이언트
client = Client()

DATASET_NAME = "map-stage-eval"


def create_dataset_from_test_cases(
    test_cases_path: str = "evaluations/datasets/test_cases.json",
):
    """test_cases.json에서 LangSmith 데이터셋 생성."""
    with open(test_cases_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 기존 데이터셋 확인
    existing = list(client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        print(f"⚠️  Dataset '{DATASET_NAME}' already exists. Deleting...")
        client.delete_dataset(dataset_id=existing[0].id)

    # 새 데이터셋 생성
    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="Daily report map stage evaluation test cases",
    )
    print(f"✓ Dataset created: {dataset.name} (id: {dataset.id})")

    # 예제 추가
    for case in data["test_cases"]:
        client.create_example(
            dataset_id=dataset.id,
            inputs={"message": case["input"], "case_id": case["id"]},
            outputs=case["expected"],
            metadata={"name": case["name"]},
        )
        print(f"  + {case['id']}: {case['name']}")

    print(f"\n✓ {len(data['test_cases'])} examples added to dataset")
    return dataset


def run_map_stage_for_eval(inputs: Dict) -> Dict:
    """LangSmith evaluate()용 타겟 함수."""
    message = TelegramMessage(
        channel_id="test",
        message_id=inputs["case_id"],
        timestamp=datetime.now(),
        text=inputs["message"],
    )

    issues = map_stage([message])

    return {
        "issues": [issue.model_dump() for issue in issues],
        "num_issues": len(issues),
        "all_text": _issues_to_text(issues),
        "all_themes": [theme for issue in issues for theme in issue.themes],
        "all_keywords": [kw for issue in issues for kw in issue.keywords],
    }


# ============================================================
# Rule-based Evaluators — metrics.py 함수를 래핑
# ============================================================

def split_accuracy(run: Run, example: Example) -> Dict:
    """이슈 분리 정확도."""
    issues = [MappedIssue(**i) for i in (run.outputs or {}).get("issues", [])]
    score = _split_accuracy(issues, example.outputs or {})
    return {"key": "split_accuracy", "score": score}


def must_split_check(run: Run, example: Example) -> Dict:
    """분리 필요 여부 충족 검사."""
    issues = [MappedIssue(**i) for i in (run.outputs or {}).get("issues", [])]
    score = _must_split_check(issues, example.outputs or {})
    return {"key": "must_split_check", "score": score}


def number_preservation(run: Run, example: Example) -> Dict:
    """숫자 보존율."""
    issues = [MappedIssue(**i) for i in (run.outputs or {}).get("issues", [])]
    score = _number_preservation(issues, example.outputs or {})
    return {"key": "number_preservation", "score": score}


def company_preservation(run: Run, example: Example) -> Dict:
    """기업명 보존율."""
    issues = [MappedIssue(**i) for i in (run.outputs or {}).get("issues", [])]
    score = _company_preservation(issues, example.outputs or {})
    return {"key": "company_preservation", "score": score}


def keyword_coverage(run: Run, example: Example) -> Dict:
    """키워드 커버리지."""
    issues = [MappedIssue(**i) for i in (run.outputs or {}).get("issues", [])]
    score = _keyword_coverage(issues, example.outputs or {})
    return {"key": "keyword_coverage", "score": score}


# ============================================================
# LLM-as-Judge Evaluator
# ============================================================

def theme_relevance_llm(run: Run, example: Example) -> Dict:
    """LLM-as-Judge로 테마 의미적 유사도 평가."""
    from langchain_core.messages import HumanMessage, SystemMessage

    outputs = run.outputs or {}
    expected = example.outputs or {}

    expected_themes = expected.get("expected_themes", [])
    if not expected_themes:
        return {"key": "theme_relevance", "score": 1.0}

    actual_themes = outputs.get("all_themes", [])
    if not actual_themes:
        return {"key": "theme_relevance", "score": 0.0}

    llm = LLMProvider.create(
        provider="anthropic",
        model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        temperature=0,
    )

    system_prompt = """당신은 테마 매칭 평가자입니다.
예상 테마와 실제 테마가 의미적으로 일치하는지 판단하세요.

규칙:
- 정확히 같은 단어가 아니어도 의미가 같으면 매칭됨
- 예: "양자보안" ≈ "Post-Quantum Cryptography" ≈ "양자암호"
- 예: "전기차 수요 둔화" ≈ "EV 시장 성장 둔화"
- 부분적으로 관련있는 것은 매칭 아님

JSON 형식으로 응답하세요."""

    user_prompt = f"""예상 테마: {expected_themes}
실제 테마: {actual_themes}

각 예상 테마가 실제 테마 중 하나와 의미적으로 일치하는지 판단하세요."""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    try:
        llm_with_output = llm.with_structured_output(ThemeMatchResult)
        result = llm_with_output.invoke(messages)
        reasoning = result.matches[0].get("reason", "") if result.matches else ""
        return {
            "key": "theme_relevance",
            "score": result.score,
            "comment": reasoning,
        }
    except Exception as e:
        print(f"⚠️  LLM 테마 평가 실패: {e}")
        return {"key": "theme_relevance", "score": 0.5}


def run_evaluation(experiment_prefix: str):
    """LangSmith evaluate() 실행."""
    print(f"\n🚀 Running evaluation: {experiment_prefix}")
    print(f"   Dataset: {DATASET_NAME}")
    print(f"   View results at: https://smith.langchain.com\n")

    results = evaluate(
        run_map_stage_for_eval,
        data=DATASET_NAME,
        evaluators=[
            split_accuracy,
            must_split_check,
            number_preservation,
            company_preservation,
            keyword_coverage,
            theme_relevance_llm,
        ],
        experiment_prefix=experiment_prefix,
    )

    print("\n" + "=" * 60)
    print("📈 EVALUATION COMPLETE")
    print("=" * 60)
    print(f"Experiment: {experiment_prefix}")
    print(f"View detailed results at: https://smith.langchain.com")

    return results


def main():
    parser = argparse.ArgumentParser(description="LangSmith Map stage 평가")
    parser.add_argument(
        "--create-dataset",
        action="store_true",
        help="test_cases.json에서 LangSmith 데이터셋 생성",
    )
    parser.add_argument(
        "--experiment",
        type=str,
        help="실험 이름 (예: v1_baseline, v2_improved)",
    )
    parser.add_argument(
        "--test-cases",
        default="evaluations/datasets/test_cases.json",
        help="테스트 케이스 파일 경로",
    )
    args = parser.parse_args()

    if args.create_dataset:
        create_dataset_from_test_cases(args.test_cases)
    elif args.experiment:
        run_evaluation(args.experiment)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
