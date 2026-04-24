"""Technical analysis chart rendering with mplfinance."""

import logging
import os
from dataclasses import dataclass
from typing import Any

import matplotlib
import pandas as pd


matplotlib.use("Agg")

logger = logging.getLogger(__name__)


@dataclass
class ChartResult:
    """Chart rendering result."""

    ticker: str
    path: str
    success: bool
    error: str = ""


def _setup_korean_font() -> str:
    """Setup Korean-capable font for matplotlib."""
    try:
        from matplotlib import font_manager

        preferred = [
            "Noto Sans CJK KR",
            "Noto Sans KR",
            "AppleGothic",
            "NanumGothic",
            "Malgun Gothic",
            "Arial Unicode MS",
        ]
        available = {f.name for f in font_manager.fontManager.ttflist}
        chosen = next((n for n in preferred if n in available), None)
        if chosen:
            matplotlib.rcParams["font.family"] = chosen
            current = list(matplotlib.rcParams.get("font.sans-serif", []))
            matplotlib.rcParams["font.sans-serif"] = [chosen, *[c for c in current if c != chosen]]
        matplotlib.rcParams["axes.unicode_minus"] = False
        return chosen or ""
    except Exception:
        return ""


def _ensure_dir(path: str) -> None:
    """Create output directory if not exists."""
    os.makedirs(path, exist_ok=True)


def _badge(ax: Any, text: str, *, xy: tuple[float, float] = (0.01, 0.96)) -> None:
    """Display label badge at panel top-left."""
    ax.text(
        xy[0],
        xy[1],
        text,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8.5,
        color="#111111",
        bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": "#DDDDDD", "alpha": 0.85},
        zorder=5,
    )


def _shade_stage2(ax: Any, df: pd.DataFrame) -> None:
    """Stage2 조건 충족 구간을 배경 음영으로 표시."""
    if "Is_Stage2" not in df.columns:
        return

    mask = df["Is_Stage2"].astype(bool).fillna(False).to_numpy()
    if mask.size == 0 or not mask.any():
        return

    idx = df.index.to_list()
    start_i: int | None = None

    # 연속된 True 구간을 찾아 음영 처리
    for i, v in enumerate(mask):
        if v and start_i is None:
            start_i = i
        if (not v or i == len(mask) - 1) and start_i is not None:
            end_i = i if v and i == len(mask) - 1 else i - 1
            ax.axvspan(idx[start_i], idx[end_i], facecolor="green", alpha=0.08, zorder=0)
            start_i = None


def _right_value_labels(ax: Any, df: pd.DataFrame) -> None:
    """Display moving average labels on the right side of price panel."""
    if df.empty:
        return
    x = df.index[-1]
    labels = [
        ("MA50", "SMA_50", "#00D1FF", 0),  # 최상단
        ("MA200", "SMA_200", "#FF2D55", -10),
        ("MA120", "SMA_120", "#FF8C00", -20),
        ("MA20", "SMA_20", "#4DA3FF", 10),
        ("MA10", "SMA_10", "#B0B0B0", 20),
        ("MA150", "SMA_150", "#8A8A8A", 30),  # 최하단
    ]
    for name, col, color, dy in labels:
        if col not in df.columns:
            continue
        try:
            y = float(df[col].iloc[-1])
        except Exception:
            continue
        if pd.isna(y):
            continue
        ax.annotate(
            name,
            xy=(x, y),
            xytext=(-6, dy),
            textcoords="offset points",
            ha="right",
            va="center",
            fontsize=8.0,
            color=color,
            bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": color, "alpha": 0.8},
            zorder=6,
        )


def _draw_support_resistance(
    ax: Any, df: pd.DataFrame, support_levels: list[dict], resistance_levels: list[dict]
) -> None:
    """Draw horizontal lines for support/resistance levels."""
    for level in support_levels[:3]:
        price = level.get("price")
        if price and not pd.isna(price):
            ax.axhline(y=price, color="green", linestyle="--", linewidth=0.7, alpha=0.5, zorder=3)

    for level in resistance_levels[:3]:
        price = level.get("price")
        if price and not pd.isna(price):
            ax.axhline(y=price, color="red", linestyle="--", linewidth=0.7, alpha=0.5, zorder=3)


def _mark_patterns(ax: Any, df: pd.DataFrame, patterns: dict[str, Any]) -> None:
    """Mark detected chart patterns with annotations."""
    for pattern_name, result in patterns.items():
        if not result.get("detected"):
            continue

        completed_date = result.get("completed_date")
        if not completed_date:
            continue

        try:
            # Find index closest to completion date
            completion_idx = pd.to_datetime(completed_date)
            if completion_idx not in df.index:
                # Find nearest
                nearest_idx = min(df.index, key=lambda x: abs(x - completion_idx))
            else:
                nearest_idx = completion_idx

            y_pos = df["High"].loc[nearest_idx] * 1.02
            ax.annotate(
                result.get("pattern_name", pattern_name),
                xy=(nearest_idx, y_pos),
                xytext=(0, 15),
                textcoords="offset points",
                ha="center",
                fontsize=7.5,
                color="#FF00FF",
                bbox={"boxstyle": "round,pad=0.3", "fc": "yellow", "alpha": 0.7},
                arrowprops={"arrowstyle": "->", "color": "#FF00FF", "lw": 1.5},
                zorder=7,
            )
        except Exception as e:
            logger.warning(f"Failed to mark pattern {pattern_name}: {e}")


def render_technical_chart(
    *,
    ticker: str,
    df: pd.DataFrame,
    indicators: dict[str, float],
    patterns: dict[str, Any] | None = None,
    price_levels: dict | None = None,
    out_dir: str = "charts",
    window_days: int = 63,
) -> ChartResult:
    """
    Render technical analysis chart with indicators, patterns, and price levels.

    Args:
        ticker: Stock ticker symbol
        df: OHLC dataframe with computed indicators
        indicators: Indicator snapshot (for compatibility, not used directly)
        patterns: Chart pattern detection results
        price_levels: Support/resistance levels
        out_dir: Output directory
        window_days: Number of days to display

    Returns:
        ChartResult with path to saved chart
    """
    try:
        import matplotlib.pyplot as plt
        import mplfinance as mpf

        _ensure_dir(out_dir)
        chosen_font = _setup_korean_font()

        # Slice window
        df_plot = df.iloc[-window_days:] if window_days > 0 else df.copy()
        if df_plot.empty:
            raise ValueError("Empty dataframe after windowing")

        # Flatten MultiIndex columns (yfinance single ticker returns MultiIndex)
        if isinstance(df_plot.columns, pd.MultiIndex):
            df_plot.columns = df_plot.columns.get_level_values(0)

        # Ensure datetime index
        if not isinstance(df_plot.index, pd.DatetimeIndex):
            df_plot.index = pd.to_datetime(df_plot.index)
        df_plot = df_plot.sort_index()

        addplots = []

        def _has_values(col: str) -> bool:
            return col in df_plot.columns and bool(df_plot[col].notna().any())

        # Moving averages (6개, 우선순위별 스타일)
        if _has_values("SMA_10"):
            addplots.append(mpf.make_addplot(df_plot["SMA_10"], color="#B0B0B0", width=0.7))
        if _has_values("SMA_20"):
            addplots.append(mpf.make_addplot(df_plot["SMA_20"], color="#4DA3FF", width=1.2))
        if _has_values("SMA_50"):
            addplots.append(mpf.make_addplot(df_plot["SMA_50"], color="#00D1FF", width=2.0))
        if _has_values("SMA_120"):
            addplots.append(mpf.make_addplot(df_plot["SMA_120"], color="#FF8C00", width=1.3))
        if _has_values("SMA_150"):
            addplots.append(mpf.make_addplot(df_plot["SMA_150"], color="#8A8A8A", width=0.7))
        if _has_values("SMA_200"):
            addplots.append(mpf.make_addplot(df_plot["SMA_200"], color="#FF2D55", width=1.8))

        # Supertrend with signal markers
        if {"SuperTrend_Up", "SuperTrend_Dn", "SuperTrend_Dir"}.issubset(df_plot.columns):
            st_dir = df_plot["SuperTrend_Dir"].astype("int64")
            st_up = df_plot["SuperTrend_Up"].where(st_dir == 1)
            st_dn = df_plot["SuperTrend_Dn"].where(st_dir == -1)

            if st_up.notna().any():
                addplots.append(
                    mpf.make_addplot(st_up, color="green", width=1.3, secondary_y=False)
                )
            if st_dn.notna().any():
                addplots.append(mpf.make_addplot(st_dn, color="red", width=1.3, secondary_y=False))

            # Buy/Sell signal markers
            buy_signal = (st_dir == 1) & (st_dir.shift(1) == -1)
            sell_signal = (st_dir == -1) & (st_dir.shift(1) == 1)

            buy_y = df_plot["SuperTrend_Up"].where(buy_signal)
            sell_y = df_plot["SuperTrend_Dn"].where(sell_signal)

            if buy_y.notna().any():
                addplots.append(
                    mpf.make_addplot(
                        buy_y,
                        type="scatter",
                        marker="o",
                        markersize=35,
                        color="green",
                    )
                )
            if sell_y.notna().any():
                addplots.append(
                    mpf.make_addplot(
                        sell_y,
                        type="scatter",
                        marker="o",
                        markersize=35,
                        color="red",
                    )
                )

        # Volume MA50
        if _has_values("Vol_SMA_50"):
            addplots.append(
                mpf.make_addplot(df_plot["Vol_SMA_50"], panel=1, color="gold", width=0.8)
            )

        panel_ratios = (6, 2)

        # MACD panel
        has_macd = {"MACD", "MACD_Signal", "MACD_Hist"}.issubset(df_plot.columns) and any(
            _has_values(c) for c in ["MACD", "MACD_Signal", "MACD_Hist"]
        )
        if has_macd:
            panel_ratios = (*panel_ratios, 2)
            addplots.append(
                mpf.make_addplot(
                    df_plot["MACD_Hist"],
                    panel=2,
                    type="bar",
                    color="#888888",
                    alpha=0.55,
                    width=0.7,
                )
            )
            addplots.append(mpf.make_addplot(df_plot["MACD"], panel=2, color="#4DA3FF", width=1.0))
            addplots.append(
                mpf.make_addplot(df_plot["MACD_Signal"], panel=2, color="#FF8C00", width=0.9)
            )

        # cRSI panel
        has_crsi = {"cRSI", "cRSI_HighBand", "cRSI_LowBand"}.issubset(
            df_plot.columns
        ) and _has_values("cRSI")
        if has_crsi:
            crsi_panel = 3 if has_macd else 2
            panel_ratios = (*panel_ratios, 2)
            addplots.append(
                mpf.make_addplot(
                    df_plot["cRSI"],
                    panel=crsi_panel,
                    color="#FF00FF",
                    width=1.0,
                    ylim=(0, 100),
                )
            )
            # Dynamic bands
            if _has_values("cRSI_LowBand"):
                addplots.append(
                    mpf.make_addplot(
                        df_plot["cRSI_LowBand"],
                        panel=crsi_panel,
                        color="#00FFFF",
                        width=0.8,
                        alpha=0.9,
                    )
                )
            if _has_values("cRSI_HighBand"):
                addplots.append(
                    mpf.make_addplot(
                        df_plot["cRSI_HighBand"],
                        panel=crsi_panel,
                        color="#00FFFF",
                        width=0.8,
                        alpha=0.9,
                    )
                )
            # 30/70 reference lines
            addplots.append(
                mpf.make_addplot(
                    pd.Series(30.0, index=df_plot.index),
                    panel=crsi_panel,
                    color="#B0B0B0",
                    width=0.8,
                    linestyle="dashed",
                    alpha=0.7,
                )
            )
            addplots.append(
                mpf.make_addplot(
                    pd.Series(70.0, index=df_plot.index),
                    panel=crsi_panel,
                    color="#B0B0B0",
                    width=0.8,
                    linestyle="dashed",
                    alpha=0.7,
                )
            )

        plot_kwargs = {
            "type": "candle",
            "volume": True,
            "style": "yahoo",
            "title": "",
            "tight_layout": True,
            "panel_ratios": panel_ratios,
            "returnfig": True,
        }
        if addplots:
            plot_kwargs["addplot"] = addplots

        fig, axes = mpf.plot(df_plot, **plot_kwargs)

        # Get primary axes by panel
        def _primary_axes_by_panel(fig):
            groups: dict[tuple[float, float], list] = {}
            for ax in fig.axes:
                pos = ax.get_position()
                key = (round(float(pos.y0), 4), round(float(pos.y1), 4))
                groups.setdefault(key, []).append(ax)

            def _score(ax):
                return len(ax.lines) + len(ax.patches) + len(ax.collections)

            panels = []
            for key in sorted(groups.keys(), key=lambda k: k[1], reverse=True):
                axes = groups[key]
                panels.append(max(axes, key=_score))
            return panels

        panels = _primary_axes_by_panel(fig)
        if panels:
            ax_price = panels[0]
            if chosen_font:
                ax_price.set_title(ticker, fontname=chosen_font)
            else:
                ax_price.set_title(ticker)
            _right_value_labels(ax_price, df_plot)

            # Stage2 shading
            _shade_stage2(ax_price, df_plot)

            # Draw support/resistance levels
            if price_levels:
                support = price_levels.get("support_levels", [])
                resistance = price_levels.get("resistance_levels", [])
                if support or resistance:
                    support_dicts = [
                        {"price": s.price} if hasattr(s, "price") else s for s in support
                    ]
                    resistance_dicts = [
                        {"price": r.price} if hasattr(r, "price") else r for r in resistance
                    ]
                    _draw_support_resistance(ax_price, df_plot, support_dicts, resistance_dicts)

            # Mark patterns
            if patterns:
                patterns_dict = {}
                for k, v in patterns.items():
                    if hasattr(v, "model_dump"):
                        patterns_dict[k] = v.model_dump()
                    elif hasattr(v, "__dict__"):
                        patterns_dict[k] = v.__dict__
                    else:
                        patterns_dict[k] = v
                _mark_patterns(ax_price, df_plot, patterns_dict)

        # Panel badges
        if len(panels) >= 2:
            _badge(panels[1], "VOL + VOL_MA50", xy=(0.01, 0.92))
        if has_macd and len(panels) >= 3:
            _badge(panels[2], "MACD(12,26,9)", xy=(0.01, 0.92))
        if has_crsi:
            crsi_panel_i = 3 if has_macd else 2
            if len(panels) > crsi_panel_i:
                _badge(panels[crsi_panel_i], "cRSI(dc=20,vib=10,lvl=10%)", xy=(0.01, 0.92))

        # Save
        filename = f"{ticker.replace('/', '_')}_technical.png"
        path = os.path.join(out_dir, filename)
        fig.savefig(path, dpi=130, bbox_inches="tight", pad_inches=0.15)
        plt.close(fig)

        return ChartResult(ticker=ticker, path=path, success=True)

    except Exception as e:
        logger.error(f"Chart rendering failed for {ticker}: {e}")
        return ChartResult(ticker=ticker, path="", success=False, error=str(e))
