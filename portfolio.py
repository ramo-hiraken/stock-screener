import yfinance as yf
import pandas as pd
from datetime import datetime
from config import PORTFOLIO_FILE, STOP_LOSS_PERCENT, load_json, save_json


def load_portfolio() -> list[dict]:
    return load_json(PORTFOLIO_FILE, [])


def save_portfolio(portfolio: list[dict]):
    save_json(PORTFOLIO_FILE, portfolio)


def add_position(code: str, shares: int, buy_price: float, note: str = "") -> dict:
    portfolio = load_portfolio()
    position = {
        "code": code,
        "shares": shares,
        "buy_price": buy_price,
        "buy_date": datetime.now().strftime("%Y-%m-%d"),
        "note": note,
    }
    portfolio.append(position)
    save_portfolio(portfolio)
    return position


def remove_position(index: int) -> bool:
    portfolio = load_portfolio()
    if 0 <= index < len(portfolio):
        portfolio.pop(index)
        save_portfolio(portfolio)
        return True
    return False


def get_portfolio_status() -> pd.DataFrame:
    portfolio = load_portfolio()
    if not portfolio:
        return pd.DataFrame()

    rows = []
    for i, pos in enumerate(portfolio):
        code = pos["code"]
        try:
            ticker = yf.Ticker(f"{code}.T")
            current = ticker.history(period="1d")["Close"].iloc[-1]
        except Exception:
            current = 0

        buy_price = pos["buy_price"]
        shares = pos["shares"]
        pnl = (current - buy_price) * shares
        pnl_pct = ((current / buy_price) - 1) * 100 if buy_price > 0 else 0
        stop_price = buy_price * (1 - STOP_LOSS_PERCENT / 100)

        rows.append({
            "No": i,
            "コード": code,
            "株数": shares,
            "取得価格": buy_price,
            "現在値": round(current, 1),
            "損益": round(pnl),
            "損益率(%)": round(pnl_pct, 2),
            "損切ライン": round(stop_price, 1),
            "要損切": "⚠️" if current <= stop_price else "",
            "取得日": pos["buy_date"],
            "メモ": pos.get("note", ""),
        })

    return pd.DataFrame(rows)
