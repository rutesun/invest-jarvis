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


def _issues_to_text(issues: List[MappedIssue]) -> str:
    """이슈 리스트를 단일 텍스트로 변환."""
    parts = []
    for issue in issues:
        parts.append(issue.title)
        parts.append(issue.summary)
        parts.append(issue.impact)
        parts.extend(issue.themes)
        parts.extend(issue.keywords)
    return " ".join(parts)


# ============================================================
# Rule-based Evaluators
# ============================================================

def split_accuracy(run: Run, example: Example) -> Dict:
    """이슈 분리 정확도."""
    outputs = run.outputs or {}
    expected = example.outputs or {}

    actual_count = outputs.get("num_issues", 0)
    min_expected = expected.get("num_issues_min", 1)
    max_expected = expected.get("num_issues_max", 1)

    score = 1.0 if min_expected <= actual_count <= max_expected else 0.0
    return {"key": "split_accuracy", "score": score}


def number_preservation(run: Run, example: Example) -> Dict:
    """숫자 보존율."""
    outputs = run.outputs or {}
    expected = example.outputs or {}

    expected_numbers = expected.get("must_preserve_numbers", [])
    if not expected_numbers:
        return {"key": "number_preservation", "score": 1.0}

    output_text = outputs.get("all_text", "")
    preserved = sum(1 for n in expected_numbers if n in output_text)
    score = preserved / len(expected_numbers)

    return {"key": "number_preservation", "score": score}


def company_preservation(run: Run, example: Example) -> Dict:
    """기업명 보존율."""
    outputs = run.outputs or {}
    expected = example.outputs or {}

    expected_companies = expected.get("must_preserve_companies", [])
    if not expected_companies:
        return {"key": "company_preservation", "score": 1.0}

    output_text = outputs.get("all_text", "")
    preserved = sum(1 for c in expected_companies if c in output_text)
    score = preserved / len(expected_companies)

    return {"key": "company_preservation", "score": score}


def keyword_coverage(run: Run, example: Example) -> Dict:
    """키워드 커버리지."""
    outputs = run.outputs or {}
    expected = example.outputs or {}

    expected_keywords = expected.get("expected_keywords", [])
    if not expected_keywords:
        return {"key": "keyword_coverage", "score": 1.0}

    output_text = outputs.get("all_text", "")
    all_keywords = outputs.get("all_keywords", [])
    search_text = output_text + " " + " ".join(all_keywords)

    covered = sum(1 for kw in expected_keywords if kw in search_text)
    score = covered / len(expected_keywords)

    return {"key": "keyword_coverage", "score": score}


# ============================================================
# LLM-as-Judge Evaluator
# ============================================================

def theme_relevance_llm(run: Run, example: Example) -> Dict:
    """LLM-as-Judge로 테마 의미적 유사도 평가."""
    from pydantic import BaseModel, Field
    from langchain_core.messages import HumanMessage, SystemMessage

    class ThemeMatchResult(BaseModel):
        score: float = Field(description="매칭 점수 (0.0 ~ 1.0)", ge=0.0, le=1.0)
        reasoning: str = Field(description="판단 근거")

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

각 예상 테마가 실제 테마 중 하나와 매칭되면 1점, 아니면 0점.
전체 예상 테마 중 매칭된 비율을 score로 반환하세요."""

    user_prompt = f"""예상 테마: {expected_themes}
실제 테마: {actual_themes}

매칭 점수와 판단 근거를 제공하세요."""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    try:
        llm_with_output = llm.with_structured_output(ThemeMatchResult)
        result = llm_with_output.invoke(messages)
        return {
            "key": "theme_relevance",
            "score": result.score,
            "comment": result.reasoning,
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
