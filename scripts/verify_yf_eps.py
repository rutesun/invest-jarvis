"""yfinance 분기/연간 EPS 소스 확인. 실행: uv run python scripts/verify_yf_eps.py AAPL"""

import sys

import yfinance as yf


def main(ticker: str) -> None:
    t = yf.Ticker(ticker)
    print("=== quarterly_income_stmt index (EPS 후보) ===")
    qis = t.quarterly_income_stmt
    if qis is not None and not qis.empty:
        eps_rows = [r for r in qis.index if "EPS" in str(r) or "Earnings Per" in str(r)]
        print("columns(분기):", [str(c.date()) for c in qis.columns][:8])
        print("EPS rows:", eps_rows)
        for r in eps_rows:
            print(f"  {r}:", [qis.loc[r, c] for c in qis.columns[:8]])
    print("=== income_stmt (annual) EPS rows ===")
    ann = t.income_stmt
    if ann is not None and not ann.empty:
        eps_rows = [r for r in ann.index if "EPS" in str(r) or "Earnings Per" in str(r)]
        print("columns(연간):", [str(c.date()) for c in ann.columns][:6])
        print("EPS rows:", eps_rows)
        for r in eps_rows:
            print(f"  {r}:", [ann.loc[r, c] for c in ann.columns[:6]])
    print("=== info trailingEps (TTM 단일) ===", t.info.get("trailingEps"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "AAPL")
