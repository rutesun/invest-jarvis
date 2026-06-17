import pandas as pd


def test_last_valid_close_returns_last_non_nan():
    """마지막 행이 NaN(당일 미완성 봉)이면 직전 유효 종가를 돌려준다."""
    from src.tools.technical.df_guards import last_valid_close

    df = pd.DataFrame({"Close": [100.0, 101.0, 102.0, float("nan")]})
    assert last_valid_close(df) == 102.0


def test_last_valid_close_normal_last_row():
    """마지막 행이 정상이면 그 값을 돌려준다."""
    from src.tools.technical.df_guards import last_valid_close

    df = pd.DataFrame({"Close": [100.0, 101.0, 102.0]})
    assert last_valid_close(df) == 102.0


def test_last_valid_close_all_nan_returns_none():
    """전부 NaN이면 None."""
    from src.tools.technical.df_guards import last_valid_close

    df = pd.DataFrame({"Close": [float("nan"), float("nan")]})
    assert last_valid_close(df) is None


def test_last_valid_close_missing_column_returns_none():
    """Close 컬럼이 없으면 None."""
    from src.tools.technical.df_guards import last_valid_close

    df = pd.DataFrame({"Open": [1.0, 2.0]})
    assert last_valid_close(df) is None


def test_last_valid_close_empty_df_returns_none():
    """빈 DataFrame이면 None."""
    from src.tools.technical.df_guards import last_valid_close

    assert last_valid_close(pd.DataFrame({"Close": []})) is None
