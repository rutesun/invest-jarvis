def test_render_module_exposes_format_deep_dive_output():
    from src.cli.analyze_render import format_deep_dive_output

    assert callable(format_deep_dive_output)


def test_main_reexports_format_deep_dive_output():
    # 기존 import 경로 호환 유지
    from src.cli.main import format_deep_dive_output

    assert callable(format_deep_dive_output)
