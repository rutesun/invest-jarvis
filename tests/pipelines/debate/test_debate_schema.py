def _walk_no_open_dict(schema: dict, path="root"):
    if isinstance(schema, dict):
        if schema.get("type") == "object" and "properties" not in schema:
            raise AssertionError(f"open dict at {path}")
        for k, v in schema.items():
            _walk_no_open_dict(v, f"{path}.{k}")
    elif isinstance(schema, list):
        for i, v in enumerate(schema):
            _walk_no_open_dict(v, f"{path}[{i}]")


def test_debate_output_models_are_strict():
    from src.llm.models import DebateAdvocacyOutput, DebateVerdictOutput

    _walk_no_open_dict(DebateAdvocacyOutput.model_json_schema())
    _walk_no_open_dict(DebateVerdictOutput.model_json_schema())


def test_debate_case_fields():
    from src.llm.models import DebateCase

    case = DebateCase(stance="bull", thesis="강세", points=["근거1", "근거2"])
    assert case.stance == "bull"
    assert len(case.points) == 2
