"""台股財經報告主流程：抓資料 → Gemini 生成 → LINE 推送

Usage:
    python main.py                # 預設：晚報 (台股收盤後)
    python main.py --mode evening # 晚報
    python main.py --mode morning # 早報 (盤前快報)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pytz
from dotenv import load_dotenv

from config import WATCHLIST
from data.fetcher_intl import (
    fetch_adr_with_premium,
    fetch_all_intl,
    fetch_premarket,
    fetch_tw_holdings_prev_close,
    fetch_us_held,
)
from data.fetcher_news import fetch_all_news
from data.fetcher_twse import fetch_all_twse, is_market_open_today
from notify.line_bot import push_text
from report.generator import generate_morning_report, generate_report

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def setup_logging(mode: str) -> None:
    today = datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y%m%d")
    log_file = LOG_DIR / f"{today}_{mode}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _safe_push(msg: str) -> None:
    try:
        push_text(msg)
    except Exception:
        logging.getLogger("main").exception("錯誤通知推送失敗")


def run_evening() -> int:
    log = logging.getLogger("main")
    tz = pytz.timezone("Asia/Taipei")
    log.info("===== 晚報啟動 =====")

    log.info("檢查台股今日是否開市...")
    if not is_market_open_today():
        log.info("今日台股休市/未開盤，不發送晚報")
        return 0
    log.info("今日有開市，繼續執行")

    current_step = "init"
    try:
        current_step = "TWSE"
        log.info("Step 1/4: 抓 TWSE 資料")
        twse = fetch_all_twse(WATCHLIST)

        current_step = "國際數據"
        log.info("Step 2/4: 抓國際數據 + 美股持股")
        intl = fetch_all_intl()
        us_held = fetch_us_held()

        current_step = "新聞 RSS"
        log.info("Step 3/4: 抓新聞 RSS")
        news = fetch_all_news()

        data = {"twse": twse, "intl": intl, "us_held": us_held, "news": news}

        date_str = datetime.now(tz).strftime("%Y%m%d")
        (LOG_DIR / f"{date_str}_evening_raw.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        current_step = "Gemini 生成"
        log.info("Step 4/4: Gemini 生成晚報")
        report = generate_report(data)
        (LOG_DIR / f"{date_str}_evening_report.txt").write_text(report, encoding="utf-8")
        log.info("晚報長度: %d 字", len(report))

        current_step = "LINE 推送"
        log.info("推送 LINE")
        push_text(report)
        log.info("===== 晚報完成 =====")
        return 0
    except Exception as e:
        log.exception("晚報失敗於 [%s]: %s", current_step, e)
        tb = traceback.format_exc().splitlines()[-3:]
        _safe_push((
            f"⚠️ 台股晚報執行失敗\n卡在：{current_step}\n"
            f"錯誤：{type(e).__name__}: {e}\n---\n" + "\n".join(tb)
        )[:1000])
        return 1


def run_morning() -> int:
    log = logging.getLogger("main")
    tz = pytz.timezone("Asia/Taipei")
    log.info("===== 早報啟動 =====")

    # 早報的「是否執行」檢查：只看是否為週一到五（國定假日台股休市時還是會跑早報，
    # 因為可能是觀察美股動向用，但若你想精準跳過國定假日，可在這加假日表）
    weekday = datetime.now(tz).weekday()
    if weekday >= 5:
        log.info("今日週末，不發送早報")
        return 0

    current_step = "init"
    try:
        current_step = "國際數據"
        log.info("Step 1/4: 抓國際數據（含 VIX、債息等）")
        intl = fetch_all_intl()

        current_step = "美股持股 + 期貨"
        log.info("Step 2/4: 抓美股持股 + 美股期貨")
        us_held = fetch_us_held()
        premarket = fetch_premarket()

        current_step = "ADR + 溢價"
        log.info("Step 3/5: 抓 ADR + 計算溢價/折價")
        adr = fetch_adr_with_premium()

        current_step = "台股持股昨收"
        log.info("Step 4/5: 抓台股持股昨收（早報基準）")
        tw_holdings = fetch_tw_holdings_prev_close(WATCHLIST)

        current_step = "新聞 RSS"
        log.info("Step 5/5: 抓新聞 RSS")
        news = fetch_all_news()

        data = {
            "intl": intl,
            "us_held": us_held,
            "premarket": premarket,
            "adr": adr,
            "tw_holdings": tw_holdings,
            "news": news,
        }

        date_str = datetime.now(tz).strftime("%Y%m%d")
        (LOG_DIR / f"{date_str}_morning_raw.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        current_step = "Gemini 生成"
        log.info("Gemini 生成早報")
        report = generate_morning_report(data)
        (LOG_DIR / f"{date_str}_morning_report.txt").write_text(report, encoding="utf-8")
        log.info("早報長度: %d 字", len(report))

        current_step = "LINE 推送"
        log.info("推送 LINE")
        push_text(report)
        log.info("===== 早報完成 =====")
        return 0
    except Exception as e:
        log.exception("早報失敗於 [%s]: %s", current_step, e)
        tb = traceback.format_exc().splitlines()[-3:]
        _safe_push((
            f"⚠️ 台股早報執行失敗\n卡在：{current_step}\n"
            f"錯誤：{type(e).__name__}: {e}\n---\n" + "\n".join(tb)
        )[:1000])
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["morning", "evening"], default="evening",
                        help="morning=盤前快報, evening=收盤後晚報（預設）")
    args = parser.parse_args()

    load_dotenv()
    setup_logging(args.mode)

    if args.mode == "morning":
        return run_morning()
    return run_evening()


if __name__ == "__main__":
    sys.exit(main())
