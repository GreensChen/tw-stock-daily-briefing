"""台股日報主流程：抓資料 → Gemini 生成 → LINE 推送"""
from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pytz
from dotenv import load_dotenv

from config import WATCHLIST
from data.fetcher_intl import fetch_all_intl
from data.fetcher_news import fetch_all_news
from data.fetcher_twse import fetch_all_twse, is_market_open_today
from notify.line_bot import push_text
from report.generator import generate_report

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def setup_logging() -> None:
    today = datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y%m%d")
    log_file = LOG_DIR / f"{today}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _safe_push(msg: str) -> None:
    """錯誤通知用：失敗也只 log，不再拋"""
    try:
        push_text(msg)
    except Exception:
        logging.getLogger("main").exception("錯誤通知推送失敗")


def run() -> int:
    load_dotenv()
    setup_logging()
    log = logging.getLogger("main")
    tz = pytz.timezone("Asia/Taipei")
    today = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    log.info("===== 台股日報啟動 %s =====", today)

    # 假日檢查：今日 TWSE 沒資料就視為休市，跳過
    log.info("檢查台股今日是否開市...")
    if not is_market_open_today():
        log.info("今日台股休市/未開盤，不發送日報")
        return 0
    log.info("今日有開市，繼續執行")

    current_step = "init"
    try:
        current_step = "TWSE"
        log.info("Step 1/4: 抓 TWSE 資料")
        twse = fetch_all_twse(WATCHLIST)

        current_step = "國際數據"
        log.info("Step 2/4: 抓國際數據")
        intl = fetch_all_intl()

        current_step = "新聞 RSS"
        log.info("Step 3/4: 抓新聞 RSS")
        news = fetch_all_news()

        data = {"twse": twse, "intl": intl, "news": news}

        # 把原始資料存檔（出問題時方便回頭看）
        date_str = datetime.now(tz).strftime("%Y%m%d")
        (LOG_DIR / f"{date_str}_raw.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        current_step = "Gemini 生成"
        log.info("Step 4/4: Gemini 生成報告")
        report = generate_report(data)
        (LOG_DIR / f"{date_str}_report.txt").write_text(report, encoding="utf-8")
        log.info("報告長度: %d 字", len(report))

        current_step = "LINE 推送"
        log.info("推送 LINE")
        push_text(report)
        log.info("===== 完成 =====")
        return 0
    except Exception as e:
        log.exception("執行失敗於 [%s]: %s", current_step, e)
        tb_short = traceback.format_exc().splitlines()[-3:]
        msg = (
            f"⚠️ 台股日報執行失敗\n"
            f"卡在：{current_step}\n"
            f"錯誤：{type(e).__name__}: {e}\n"
            f"---\n" + "\n".join(tb_short)
        )
        _safe_push(msg[:1000])  # LINE 訊息壓縮
        return 1


if __name__ == "__main__":
    sys.exit(run())
