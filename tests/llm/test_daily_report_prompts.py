# tests/llm/test_daily_report_prompts.py
from src.llm.prompts.daily_report import DailyReportPrompts


def test_map_issues_prompt_includes_themes_and_messages():
    prompt = DailyReportPrompts.map_issues(
        known_themes="CPO/광통신\nAI 반도체",
        messages="[101] 엔비디아 실적 호조",
    )
    assert "CPO/광통신" in prompt
    assert "AI 반도체" in prompt
    assert "[101] 엔비디아 실적 호조" in prompt
    assert "theme" in prompt
    assert "tickers" in prompt
    assert "sentiment" in prompt


def test_merge_themes_prompt_includes_both_lists():
    prompt = DailyReportPrompts.merge_themes(
        known_themes="CPO/광통신\nAI 반도체",
        new_themes="광통신\nco-packaged optics\n방산",
    )
    assert "CPO/광통신" in prompt
    assert "co-packaged optics" in prompt
    assert "매핑" in prompt


def test_catalyst_prompt_includes_themes_json():
    prompt = DailyReportPrompts.catalyst(
        themes_json='[{"name": "CPO/광통신", "stocks": ["LITE", "COHR"]}]',
    )
    assert "LITE" in prompt
    assert "NewsTool" in prompt


def test_synthesize_prompt_includes_all_sections():
    prompt = DailyReportPrompts.synthesize(
        macro="VIX 18.2",
        news="SPY rises 1%",
        themes="CPO/광통신: bull",
        catalysts="LITE: 실적 호조",
    )
    assert "VIX 18.2" in prompt
    assert "SPY rises 1%" in prompt
    assert "CPO/광통신" in prompt
    assert "LITE" in prompt
    assert "10줄 이내" in prompt
