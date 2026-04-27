"""用 Gemini Flash 產生台股日報"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

import google.generativeai as genai
import pytz

from config import GEMINI_MODEL
from utils import retry

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一位資深財經分析師，風格參考「游庭皓的財經皓角」：
- 用總經框架串聯國際局勢和台股
- 不只堆砌數據，要給出「所以呢？」的判讀
- 從宏觀到微觀：國際 → 大盤 → 個股
- 語氣專業但不生硬，像跟朋友聊市場
- 全程使用繁體中文

【嚴格格式要求】（LINE 純文字，不支援 Markdown，務必遵守）
- 第一行必須是標題：「📈 X月X日 台股日報」（依當天日期，例如「📈 4月27日 台股日報」），下一行空白，接著直接從「🌍 Ch.1 國際市場總覽」開始
- 不要有任何開場白、寒暄、問候語（「哈囉」「大家好」「各位朋友」「老朋友」這類都禁止）
- 不要在報告開頭做整段的總結預告
- **絕對禁止使用 Markdown 語法**：不要用 ** 粗體、不要用 ## 標題、不要用 * 或 - 開頭的 markdown bullet（LINE 不會渲染，會變成醜醜的星號）
- 需要強調時：直接換行 + 用「」框住關鍵詞，或開新一段
- 需要分點時：用「・」當 bullet，每點獨立一行（例如「・台積電：今日 +5%...」），絕對不要用「* **xxx**：」
- 章節用 emoji 開頭、章節之間用一行 ─────────── 分隔
- 數字精準引用，分析要有觀點，不要只是念數字
- 最後一行加免責聲明：「⚠️ 本報告由 AI 自動生成，僅供參考，不構成投資建議。」"""


REPORT_TEMPLATE = """請依下列資料生成台股日報（資料日期：{date_str}），格式如下（LINE 純文字、不能用 Markdown）：

📈 X月X日 台股日報

🌍 Ch.1 國際市場總覽
（美股四大、債息、美元、VIX、原油黃金。判讀對台股的意涵）
───────────
📊 Ch.2 台股大盤
（加權指數、三大法人、強弱判讀）
───────────
🔍 Ch.3 觀察清單
（每檔個股用「・」開頭當第一層 bullet，下一層內容用「　◦ 」（全形空白 + 空心圓 + 半形空格）當第二層 bullet。範例：
・元大台灣50（0050）
　◦ 今日收：89.95 元（+3.6 元），成交 12.9 萬張。外資大買 3,123 萬股
　◦ 觀察重點：xxx
・台積電（2330）
　◦ 今日收：xxx
　◦ 觀察重點：xxx
）
───────────
📰 Ch.4 今日重要新聞
（挑 3-5 則最關鍵，標題用「・」開頭，「這代表什麼」用「　◦ 」當第二層 bullet。範例：
・台積電衝上股號價位 2,330 元
　◦ 這代表什麼：xxx
）
───────────
💡 Ch.5 明日觀察重點
（用「・」開頭分點，國際面/台股面）
───────────
⚠️ 本報告由 AI 自動生成，僅供參考，不構成投資建議。

=== 原始資料 ===

【國際市場】
{intl_block}

【台股大盤】
{market_block}

【三大法人買賣超（億元）】
{instit_block}

【觀察清單個股】
{stocks_block}

【新聞 RSS（{news_count} 則）】
{news_block}
"""


def _fmt_intl(intl: list[dict]) -> str:
    lines = []
    for r in intl:
        if "error" in r:
            lines.append(f"- {r.get('name')} ({r['ticker']}): 抓取失敗")
            continue
        ch = r.get("change_pct")
        ch_str = f"{ch:+.2f}%" if ch is not None else "N/A"
        lines.append(f"- {r['name']} ({r['ticker']}): {r['close']} ({ch_str}) [{r.get('as_of','')}]")
    return "\n".join(lines)


def _fmt_market(market: dict) -> str:
    if "error" in market:
        return f"（抓取失敗：{market['error']}）"
    close = market.get("taiex_close")
    change = market.get("change")
    return f"加權指數：{close}（{change:+.2f}）資料日期：{market.get('date')}"


def _fmt_instit(instit: dict) -> str:
    if "error" in instit:
        return f"（抓取失敗：{instit['error']}）"
    return (f"外資：{instit.get('foreign')}\n"
            f"投信：{instit.get('trust')}\n"
            f"自營商：{instit.get('dealer')}\n"
            f"合計：{instit.get('total')}")


def _fmt_stocks(stocks: list[dict]) -> str:
    blocks = []
    for s in stocks:
        q = s.get("quote", {})
        i = s.get("instit", {})
        if "error" in q:
            blocks.append(f"- {s['name']} ({s['code']})：行情抓取失敗")
            continue
        instit_line = ""
        if "error" not in i:
            f, t, d = i.get("foreign"), i.get("trust"), i.get("dealer")
            instit_line = f"\n  法人(股)：外{f} 投信{t} 自營{d}"
        blocks.append(
            f"- {s['name']} ({s['code']}) {q.get('trade_date')}：\n"
            f"  開{q.get('open')} 高{q.get('high')} 低{q.get('low')} 收{q.get('close')} "
            f"漲跌{q.get('change')} 成交張{q.get('volume_lots')}{instit_line}"
        )
    return "\n".join(blocks)


def _fmt_news(news: list[dict], limit: int = 15) -> str:
    lines = []
    for n in news[:limit]:
        lines.append(f"- [{n['source']}] {n['title']}\n  {n.get('summary','')[:150]}")
    return "\n".join(lines)


def build_prompt(data: dict[str, Any]) -> str:
    tz = pytz.timezone("Asia/Taipei")
    today = datetime.now(tz).strftime("%Y-%m-%d (%A)")
    twse = data.get("twse", {})
    return REPORT_TEMPLATE.format(
        date_str=today,
        intl_block=_fmt_intl(data.get("intl", [])),
        market_block=_fmt_market(twse.get("market", {})),
        instit_block=_fmt_instit(twse.get("institutional", {})),
        stocks_block=_fmt_stocks(twse.get("stocks", [])),
        news_count=len(data.get("news", [])),
        news_block=_fmt_news(data.get("news", [])),
    )


@retry(times=3, delay=5.0)
def generate_report(data: dict[str, Any]) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 未設定")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)
    prompt = build_prompt(data)
    logger.info("Gemini prompt 長度: %d 字元", len(prompt))
    resp = model.generate_content(prompt)
    return resp.text.strip()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    from config import WATCHLIST
    from data.fetcher_twse import fetch_all_twse
    from data.fetcher_intl import fetch_all_intl
    from data.fetcher_news import fetch_all_news

    data = {
        "twse": fetch_all_twse(WATCHLIST),
        "intl": fetch_all_intl(),
        "news": fetch_all_news(),
    }
    print("=== PROMPT ===")
    print(build_prompt(data))
    print("\n=== REPORT ===")
    print(generate_report(data))
