from src.providers.index_provider import index_symbol_for


def test_index_symbol_mapping():
    assert index_symbol_for("005930.KS") == "^KS11"
    assert index_symbol_for("035720.KQ") == "^KQ11"
    assert index_symbol_for("AAPL") == "^GSPC"
    assert index_symbol_for("005930") == "^KS11"  # 6자리 → 기본 코스피
