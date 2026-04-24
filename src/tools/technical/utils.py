# src/tools/technical/utils.py

import pandas as pd


def find_last_occurrence(
    df: pd.DataFrame, column: str, target_value: float, tolerance: float = 0.001
) -> int | None:
    """DataFrame에서 특정 값이 마지막으로 나타난 인덱스 찾기

    Args:
        df: 데이터프레임
        column: 검색할 컬럼명
        target_value: 찾을 값
        tolerance: 허용 오차 (±0.1% = 0.001)

    Returns:
        마지막 발생 인덱스 (없으면 None)
    """
    mask = (df[column] - target_value).abs() / target_value <= tolerance
    matches = df.index[mask]

    if len(matches) == 0:
        return None

    # Return integer index, not label
    return df.index.get_loc(matches[-1])


def create_flat_price_series(days: int, price: float) -> pd.DataFrame:
    """평평한 가격 시계열 생성 (횡보)"""
    import numpy as np

    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq="D")
    noise = np.random.normal(0, price * 0.001, days)

    return pd.DataFrame(
        {
            "Open": price + noise,
            "High": price + abs(noise),
            "Low": price - abs(noise),
            "Close": price + noise * 0.5,
        },
        index=dates,
    )


def create_noisy_series(days: int, base: float, noise: float = 0.02) -> pd.DataFrame:
    """노이즈가 있는 시계열 생성"""
    import numpy as np

    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq="D")
    noise_values = np.random.normal(0, base * noise, days)

    return pd.DataFrame(
        {
            "Open": base + noise_values,
            "High": base + abs(noise_values) * 1.2,
            "Low": base - abs(noise_values) * 1.2,
            "Close": base + noise_values * 0.8,
        },
        index=dates,
    )


def create_random_walk(days: int, start: float) -> pd.DataFrame:
    """랜덤워크 시계열 생성"""
    import numpy as np

    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq="D")
    returns = np.random.normal(0.001, 0.02, days)
    prices = start * np.exp(np.cumsum(returns))

    return pd.DataFrame(
        {
            "Open": prices,
            "High": prices * 1.01,
            "Low": prices * 0.99,
            "Close": prices,
        },
        index=dates,
    )
