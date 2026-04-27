"""國際市場數據抓取（yfinance）"""
from __future__ import annotations

import logging
from typing import Any

import yfinance as yf

from config import INTL_TICKERS, US_HELD

logger = logging.getLogger(__name__)


def fetch_one(ticker: str) -> dict[str, Any]:
    """抓單一商品最近兩日，算當日漲跌"""
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if hist.empty or len(hist) < 1:
            return {"ticker": ticker, "error": "no data"}
        last = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else None
        close = float(last["Close"])
        change_pct = None
        change = None
        if prev is not None:
            prev_close = float(prev["Close"])
            change = round(close - prev_close, 4)
            change_pct = round((close - prev_close) / prev_close * 100, 2)
        return {
            "ticker": ticker,
            "close": round(close, 2),
            "change": change,
            "change_pct": change_pct,
            "as_of": str(hist.index[-1].date()),
        }
    except Exception as e:
        logger.exception("yfinance fetch %s failed", ticker)
        return {"ticker": ticker, "error": str(e)}


def fetch_all_intl() -> list[dict[str, Any]]:
    out = []
    for ticker, name in INTL_TICKERS.items():
        row = fetch_one(ticker)
        row["name"] = name
        out.append(row)
    return out


def fetch_us_held() -> list[dict[str, Any]]:
    """抓美股持有部位（QQQ/SPY/NVDA 等）"""
    out = []
    for item in US_HELD:
        row = fetch_one(item["ticker"])
        row["name"] = item["name"]
        out.append(row)
    return out


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch_all_intl(), ensure_ascii=False, indent=2))
