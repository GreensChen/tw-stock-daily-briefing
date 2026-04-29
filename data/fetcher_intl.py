"""國際市場數據抓取（yfinance）"""
from __future__ import annotations

import logging
from typing import Any

import yfinance as yf

from config import ADR_TICKERS, INTL_TICKERS, PREMARKET_TICKERS, US_HELD

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


def fetch_premarket() -> list[dict[str, Any]]:
    """美股期貨（盤後 → 早報時的延伸情緒指標）"""
    out = []
    for ticker, name in PREMARKET_TICKERS.items():
        row = fetch_one(ticker)
        row["name"] = name
        out.append(row)
    return out


def fetch_adr_with_premium() -> list[dict[str, Any]]:
    """抓 ADR 並計算 vs TW 普通股的溢價/折價（預判開盤方向）"""
    # 先拿匯率
    fx = fetch_one("USDTWD=X")
    usdtwd = fx.get("close")

    out = []
    for item in ADR_TICKERS:
        adr_data = fetch_one(item["adr"])
        tw_data = fetch_one(item["tw_code"])
        row = {
            "adr": item["adr"],
            "name": item["name"],
            "tw_name": item["tw_name"],
            "tw_code": item["tw_code"].replace(".TW", ""),
            "ratio": item["ratio"],
        }
        if "error" not in adr_data:
            row["adr_close_usd"] = adr_data.get("close")
            row["adr_change_pct"] = adr_data.get("change_pct")
            row["adr_as_of"] = adr_data.get("as_of")
        if "error" not in tw_data:
            row["tw_prev_close"] = tw_data.get("close")
            row["tw_as_of"] = tw_data.get("as_of")

        # 換算 ADR 對應的 TW 理論價 + 溢價/折價
        # 公式：1 ADR = ratio 股普通股 → 單股美元 = ADR / ratio → × 匯率 = 單股台幣
        if (usdtwd and row.get("adr_close_usd") and row.get("tw_prev_close")):
            implied_tw = row["adr_close_usd"] / item["ratio"] * usdtwd
            premium_pct = (implied_tw / row["tw_prev_close"] - 1) * 100
            row["usdtwd"] = round(usdtwd, 3)
            row["implied_tw_price"] = round(implied_tw, 2)
            row["premium_pct"] = round(premium_pct, 2)
        out.append(row)
    return out


def fetch_tw_holdings_prev_close(watchlist: list[dict]) -> list[dict[str, Any]]:
    """抓台股持股的最近收盤價（早報用，台股還沒開盤時當基準）"""
    out = []
    for item in watchlist:
        ticker = f"{item['code']}.TW"
        row = fetch_one(ticker)
        out.append({
            "code": item["code"],
            "name": item["name"],
            "prev_close": row.get("close") if "error" not in row else None,
            "as_of": row.get("as_of") if "error" not in row else None,
            "error": row.get("error"),
        })
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
