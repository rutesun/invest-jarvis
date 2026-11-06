"""현재 기술 분석 데이터만 사용하는 일회성 check 차트."""

import re
from pathlib import Path
from tempfile import TemporaryDirectory

from src.tools.technical.charting import render_technical_chart
from src.tools.technical.components.pattern_engine import PatternEngine
from src.tools.technical.models import TechnicalResult
from src.tools.technical.price_levels import get_fibonacci_base_points, identify_key_levels


def render_check_chart(ticker: str, technical: TechnicalResult) -> tuple[bytes | None, str | None]:
    """기존 renderer의 200봉 차트를 메모리로 읽고 임시 파일을 정리한다."""
    raw = getattr(technical, "raw_dataframe", None)
    if raw is None or raw.empty:
        return None, "차트 미생성 — 현재 기술 분석의 raw 데이터가 없습니다."
    try:
        df = raw.copy(deep=True)
        patterns = PatternEngine().detect(df, technical.snapshot)
        high, low = get_fibonacci_base_points(df, technical.snapshot)
        levels = identify_key_levels(
            snapshot=technical.snapshot,
            pattern_results=patterns,
            lookback_high=high,
            lookback_low=low,
        )
        # ticker는 renderer에서 파일명에도 쓰이므로 외부 경로 문자를 허용하지 않는다.
        safe_ticker = re.sub(r"[^A-Za-z0-9_-]", "_", ticker)
        if ticker.endswith((".KS", ".KQ")):
            safe_ticker = safe_ticker[:-3] + ticker[-3:]
        with TemporaryDirectory(prefix="jarvis-check-chart-") as directory:
            result = render_technical_chart(
                ticker=safe_ticker or "CHECK",
                df=df,
                indicators=technical.snapshot.model_dump(),
                patterns=patterns,
                price_levels={
                    "support_levels": levels.support_levels,
                    "resistance_levels": levels.resistance_levels,
                },
                out_dir=directory,
                window_days=200,
            )
            if not result.success:
                return None, f"차트 생성 실패: {result.error}"
            png = Path(result.path).read_bytes()
            if not png.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("PNG 형식이 아닌 차트 결과")
            return png, None
    except Exception as exc:
        return None, f"차트 생성 실패: {type(exc).__name__}: {exc}"
