"""TWSE 台股數據抓取：大盤、三大法人、個股"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import pytz
import requests

logger = logging.getLogger(__name__)

TWSE_BASE = "https://www.twse.com.tw"
TPEX_BASE = "https://www.tpex.org.tw"
TIMEOUT = 15
HEADERS = {"User-Agent": "Mozilla/5.0 (tw-stock-daily/1.0)"}


def _today_roc_date() -> str:
    """yyyymmdd（西元）— TWSE 多數新版 API 用這個格式"""
    return datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y%m%d")


def _recent_business_days(start: str | None = None, n: int = 5) -> list[str]:
    """從 start 往回推 n 個工作日（含 start）— 用來 fallback"""
    base = datetime.strptime(start, "%Y%m%d") if start else datetime.now(pytz.timezone("Asia/Taipei"))
    days = []
    d = base
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return days


def _get_json(url: str, params: dict | None = None) -> dict:
    resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    ctype = resp.headers.get("Content-Type", "")
    if "json" not in ctype.lower():
        raise ValueError(f"Expected JSON, got {ctype}: {resp.text[:200]}")
    return resp.json()


def fetch_market_index(date: str | None = None) -> dict[str, Any]:
    """加權指數收盤行情。回傳 {date, taiex_close, change, volume_billion, up_count, down_count}"""
    date = date or _today_roc_date()
    url = f"{TWSE_BASE}/exchangeReport/MI_INDEX"
    data = _get_json(url, {"response": "json", "date": date, "type": "IND"})
    if data.get("stat") != "OK":
        raise RuntimeError(f"TWSE MI_INDEX failed: {data.get('stat')}")

    result = {"date": date, "taiex_close": None, "change": None,
              "volume_billion": None, "up_count": None, "down_count": None}

    for table in data.get("tables", []):
        title = table.get("title") or ""
        if "價格指數" not in title:
            continue
        for row in table.get("data", []):
            if row and str(row[0]).strip() == "發行量加權股價指數":
                try:
                    result["taiex_close"] = float(str(row[1]).replace(",", ""))
                    sign = -1 if "green" in str(row[2]) else 1
                    result["change"] = round(sign * float(str(row[3]).replace(",", "")), 2)
                except (ValueError, IndexError):
                    pass
                break

    if result["taiex_close"] is None:
        raise RuntimeError(f"TWSE MI_INDEX {date} 找不到加權指數資料（可能尚未收盤）")
    return result


def fetch_institutional(date: str | None = None) -> dict[str, Any]:
    """三大法人買賣超總額。回傳 {foreign, trust, dealer, total}（單位：億）"""
    date = date or _today_roc_date()
    url = f"{TWSE_BASE}/fund/BFI82U"
    data = _get_json(url, {"response": "json", "dayDate": date, "type": "day"})
    if data.get("stat") != "OK":
        raise RuntimeError(f"TWSE BFI82U failed: {data.get('stat')}")

    result = {"foreign": None, "trust": None, "dealer": None, "total": None}
    dealer_sum = 0.0
    dealer_seen = False
    for row in data.get("data", []):
        name = row[0]
        try:
            net = float(str(row[3]).replace(",", "")) / 1e8  # 元 → 億
        except (ValueError, IndexError):
            continue
        if "外資及陸資" in name:
            result["foreign"] = round(net, 2)
        elif name.strip() == "投信":
            result["trust"] = round(net, 2)
        elif "自營商" in name and "外資自營商" not in name:
            dealer_sum += net
            dealer_seen = True
        elif name.strip() == "合計":
            result["total"] = round(net, 2)

    if dealer_seen:
        result["dealer"] = round(dealer_sum, 2)
    return result


def fetch_stock_quote(stock_code: str, date: str | None = None) -> dict[str, Any]:
    """個股當日行情。回傳 {code, open, high, low, close, change, volume_lots}"""
    date = date or _today_roc_date()
    url = f"{TWSE_BASE}/exchangeReport/STOCK_DAY"
    data = _get_json(url, {"response": "json", "date": date, "stockNo": stock_code})
    if data.get("stat") != "OK":
        raise RuntimeError(f"TWSE STOCK_DAY {stock_code} failed: {data.get('stat')}")

    rows = data.get("data", [])
    if not rows:
        return {"code": stock_code, "error": "no data"}
    last = rows[-1]
    # ['日期', '成交股數', '成交金額', '開盤', '最高', '最低', '收盤', '漲跌價差', '成交筆數']
    def num(s):
        return float(str(s).replace(",", "")) if s not in ("", "--") else None
    return {
        "code": stock_code,
        "trade_date": last[0],
        "open": num(last[3]),
        "high": num(last[4]),
        "low": num(last[5]),
        "close": num(last[6]),
        "change": num(last[7]),
        "volume_lots": int(num(last[1]) / 1000) if num(last[1]) else None,
    }


def fetch_stock_institutional(stock_code: str, date: str | None = None) -> dict[str, Any]:
    """個股三大法人買賣超（張）。回傳 {code, foreign, trust, dealer}"""
    date = date or _today_roc_date()
    url = f"{TWSE_BASE}/fund/T86"
    data = _get_json(url, {"response": "json", "date": date, "selectType": "ALL"})
    if data.get("stat") != "OK":
        raise RuntimeError(f"TWSE T86 failed: {data.get('stat')}")

    fields = data.get("fields", [])
    for row in data.get("data", []):
        if row[0].strip() == stock_code:
            def get(field_name):
                for i, f in enumerate(fields):
                    if field_name in f:
                        try:
                            return int(str(row[i]).replace(",", ""))
                        except (ValueError, IndexError):
                            return None
                return None
            return {
                "code": stock_code,
                "foreign": get("外陸資買賣超股數") or get("外資買賣超"),
                "trust": get("投信買賣超"),
                "dealer": get("自營商買賣超股數") or get("自營商買賣超"),
            }
    return {"code": stock_code, "error": "not found"}


def is_market_open_today() -> bool:
    """檢查台股今日是否開市（用 MI_INDEX 判斷）。
    20:30 跑時，若今日有資料代表有開市；無資料代表休市/假日。"""
    today = _today_roc_date()
    try:
        fetch_market_index(today)
        return True
    except Exception:
        return False


def _try_with_fallback(fn, *args, **kwargs):
    """對 TWSE API 自動 fallback 到前面工作日（最多 5 個）"""
    last_err = None
    for date in _recent_business_days():
        try:
            return fn(*args, date=date, **kwargs)
        except Exception as e:
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("all dates failed")


def fetch_all_twse(watchlist: list[dict]) -> dict[str, Any]:
    """一次抓完所有台股資料（含工作日 fallback）"""
    out: dict[str, Any] = {}
    try:
        out["market"] = _try_with_fallback(fetch_market_index)
    except Exception as e:
        logger.exception("fetch_market_index failed")
        out["market"] = {"error": str(e)}

    try:
        out["institutional"] = _try_with_fallback(fetch_institutional)
    except Exception as e:
        logger.exception("fetch_institutional failed")
        out["institutional"] = {"error": str(e)}

    out["stocks"] = []
    for item in watchlist:
        code = item["code"]
        entry = {"code": code, "name": item["name"]}
        try:
            entry["quote"] = fetch_stock_quote(code)
        except Exception as e:
            logger.exception("fetch_stock_quote %s failed", code)
            entry["quote"] = {"error": str(e)}
        try:
            entry["instit"] = _try_with_fallback(fetch_stock_institutional, code)
        except Exception as e:
            logger.exception("fetch_stock_institutional %s failed", code)
            entry["instit"] = {"error": str(e)}
        out["stocks"].append(entry)
    return out


if __name__ == "__main__":
    import json
    from config import WATCHLIST
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch_all_twse(WATCHLIST), ensure_ascii=False, indent=2))
