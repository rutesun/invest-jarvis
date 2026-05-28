from __future__ import annotations

from src.pipelines.stock_report.taxonomy import build_match_dictionary, load_taxonomy_registry


def _maps(text: str) -> tuple[str, tuple[str, str] | None]:
    registry = load_taxonomy_registry("config/stock_report_vocabulary.yaml")
    category_map, theme_map = build_match_dictionary(registry)
    key = text.lower()
    return category_map.get(key, "unclassified"), theme_map.get(key)


def test_taxonomy_expanded_aliases_map_to_expected_categories_and_themes():
    assert _maps("optical networking") == ("AI인프라", ("AI인프라", "광통신/네트워크"))
    assert _maps("광통신") == ("AI인프라", ("AI인프라", "광통신/네트워크"))
    assert _maps("AI 글라스") == ("디스플레이/광학", ("디스플레이/광학", "AR/스마트글라스"))
    assert _maps("농기계") == ("산업재/기계", ("산업재/기계", "농기계"))
    assert _maps("항공주") == ("운송/물류", ("운송/물류", "항공/여행"))
    assert _maps("SMR") == ("원전/전력인프라", ("원전/전력인프라", "원전/SMR"))
    assert _maps("LNG 보냉자재") == ("조선/LNG기자재", ("조선/LNG기자재", "LNG 화물창/보냉"))
    assert _maps("희토류") == ("철강/소재", ("철강/소재", "희토류/핵심광물"))
    assert _maps("ETF") == ("금융상품", ("금융상품", "ETF/ETN"))
    assert _maps("현물 ETF") == ("금융상품", ("금융상품", "ETF/ETN"))
    assert _maps("비트코인 현물 ETF") == ("암호화폐", ("암호화폐", "비트코인/이더리움"))
    assert _maps("소프트웨어") == (
        "소프트웨어/SaaS",
        ("소프트웨어/SaaS", "엔터프라이즈 소프트웨어"),
    )
