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
- 第一行必須是標題：依報告類型而定，下方模板會明確指定（例如「📈 2026.04.29 財經晚報」或「🌅 2026.04.29 財經早報」），下一行空白，接著從第一個章節開始
- 不要有任何開場白、寒暄、問候語（「哈囉」「大家好」「各位朋友」「老朋友」這類都禁止）
- 不要在報告開頭做整段的總結預告
- **絕對禁止使用 Markdown 語法**：不要用 ** 粗體、不要用 ## 標題、不要用 * 或 - 開頭的 markdown bullet（LINE 不會渲染，會變成醜醜的星號）
- 需要強調時：直接換行 + 用「」框住關鍵詞，或開新一段
- 需要分點時：用「・」當 bullet，每點獨立一行（例如「・台積電：今日 +5%...」），絕對不要用「* **xxx**：」
- 章節用 emoji 開頭、章節之間用一行 ─────────── 分隔
- 數字精準引用，分析要有觀點，不要只是念數字
- 最後一行加免責聲明：「⚠️ 本報告由 AI 自動生成，僅供參考，不構成投資建議。」"""


REPORT_TEMPLATE = """請依下列資料生成「財經晚報」（資料日期：{date_str}），格式如下（LINE 純文字、不能用 Markdown）：

{date_hint}

📈 YYYY.MM.DD 財經晚報

🌍 Ch.1 國際市場總覽（{last_us_date}）
（美股四大、債息、美元、VIX、原油黃金。判讀對台股的意涵）
───────────
📊 Ch.2 台股大盤
（加權指數、三大法人、強弱判讀）
───────────
🔍 Ch.3 觀察清單（持有部位）
（先列台股，再列美股。每檔用「・」開頭當第一層 bullet，下一層內容用「　◦ 」當第二層。範例：
・元大台灣50（0050）
　◦ 今日收：89.95 元（+3.6 元），成交 12.9 萬張。外資大買 3,123 萬股
　◦ 觀察重點：xxx
・輝達（NVDA）
　◦ 今日收：xxx
　◦ 觀察重點：xxx
）
───────────
🌎 Ch.4 外部機會（動態挑選）
（從今天的新聞、國際市場動向、或產業話題中，動態挑出 2-3 檔【非持有部位】但值得關注的標的，可以是美股、台股、ETF、或概念股族群。**禁止固定推薦同一批股票**，每天/每週要根據當前最熱話題變動。範例：
・特斯拉（TSLA）— 今日新聞主題：xxx
　◦ 為何值得關注：xxx
　◦ 跟你持股的關聯：xxx
）
───────────
📰 Ch.5 今日重要新聞
（挑 3-5 則最關鍵，標題用「・」開頭，「這代表什麼」用「　◦ 」當第二層 bullet）
───────────
💡 Ch.6 明日觀察重點
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

【觀察清單個股 - 台股】
{stocks_block}

【觀察清單個股 - 美股持有】
{us_held_block}

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


def _fmt_tw_holdings(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        if r.get("error"):
            lines.append(f"- {r['name']} ({r['code']}): 抓取失敗")
            continue
        lines.append(f"- {r['name']} ({r['code']}): 收 {r['prev_close']} 元 [{r.get('as_of','')}]")
    return "\n".join(lines)


def _fmt_premarket(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        if "error" in r:
            lines.append(f"- {r.get('name')} ({r['ticker']}): 抓取失敗")
            continue
        ch = r.get("change_pct")
        ch_str = f"{ch:+.2f}%" if ch is not None else "N/A"
        lines.append(f"- {r['name']} ({r['ticker']}): {r['close']} ({ch_str})")
    return "\n".join(lines)


def _fmt_adr(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        ch = r.get("adr_change_pct")
        ch_str = f"{ch:+.2f}%" if ch is not None else "N/A"
        adr_line = f"- {r['name']} ({r['adr']}): {r.get('adr_close_usd')} 美元 ({ch_str})"
        if r.get("implied_tw_price") and r.get("tw_prev_close"):
            adr_line += (
                f"\n  ↳ 換算理論價 {r['implied_tw_price']} 元 vs 台股昨收 {r['tw_prev_close']} 元 "
                f"（{r['tw_name']} {r['tw_code']}），溢/折價 {r.get('premium_pct'):+.2f}%"
            )
        lines.append(adr_line)
    return "\n".join(lines)


def _fmt_us_held(us_held: list[dict]) -> str:
    lines = []
    for r in us_held:
        if "error" in r:
            lines.append(f"- {r.get('name')} ({r['ticker']}): 抓取失敗")
            continue
        ch = r.get("change_pct")
        ch_str = f"{ch:+.2f}%" if ch is not None else "N/A"
        lines.append(f"- {r['name']} ({r['ticker']}): {r['close']} ({ch_str}) [{r.get('as_of','')}]")
    return "\n".join(lines)


def _fmt_news(news: list[dict], limit: int = 15) -> str:
    lines = []
    for n in news[:limit]:
        lines.append(f"- [{n['source']}] {n['title']}\n  {n.get('summary','')[:150]}")
    return "\n".join(lines)


def build_prompt(data: dict[str, Any]) -> str:
    tz = pytz.timezone("Asia/Taipei")
    today = datetime.now(tz).strftime("%Y-%m-%d (%A)")
    twse = data.get("twse", {})

    # 自動偵測實際資料日期，避免連假後寫錯「昨收」
    last_us_date = _latest_date(data.get("intl", []))
    last_tw_date = twse.get("market", {}).get("date", "")
    if not last_tw_date:
        last_tw_date = _latest_date(data.get("us_held", []))

    date_hint = ""
    if last_us_date:
        date_hint += f"・美股最近交易日：{last_us_date}\n"
    if last_tw_date:
        date_hint += f"・台股本次資料日期：{last_tw_date}\n"
    if date_hint:
        date_hint = (
            "【重要】描述各市場收盤時，請用實際日期（如「MM/DD 收」），"
            "不要籠統說「昨收」（可能已隔假日）：\n" + date_hint
        )

    return REPORT_TEMPLATE.format(
        date_str=today,
        date_hint=date_hint,
        last_us_date=last_us_date or "最近交易日",
        intl_block=_fmt_intl(data.get("intl", [])),
        market_block=_fmt_market(twse.get("market", {})),
        instit_block=_fmt_instit(twse.get("institutional", {})),
        stocks_block=_fmt_stocks(twse.get("stocks", [])),
        us_held_block=_fmt_us_held(data.get("us_held", [])),
        news_count=len(data.get("news", [])),
        news_block=_fmt_news(data.get("news", [])),
    )


MORNING_TEMPLATE = """請依下列資料生成「財經早報」（資料時間：{date_str}），格式（LINE 純文字、不能用 Markdown）：

{date_hint}

🌅 YYYY.MM.DD 財經早報

🌙 Ch.1 美股 {last_us_date} 表現
（道瓊、S&P 500、NASDAQ、費半 SOX 收盤；用「・」第一層、「　◦ 」第二層；尤其強調費半對台股半導體的訊號）
───────────
💵 Ch.2 重要指標
（殖利率、美元 DXY、VIX、原油、黃金。各指標一行，最後加一句綜合判讀對台股風險偏好的影響）
───────────
🔍 Ch.3 持有部位夜間動向
（要對【每一檔台股持股】+【每一檔美股持股】都做分析，不可遺漏任何一檔。每檔用「・」開頭，下面用「　◦ 」第二層。

對台股持股，根據昨夜美股傳導訊號（費半、AI 巨頭、ADR 溢價/折價）給出今日預判，特別是：
- 0050、006208 → 看大盤整體（S&P 500 + SOX 走勢）
- 00895 → 看 EV 概念股（TSLA 為主）
- 2330（台積電）→ 直接看 TSM ADR 溢價/折價
- 2454（聯發科）→ 看 AI 晶片族群（NVDA、AVGO、AMD）

範例：
・元大台灣50（0050）
　◦ {last_tw_date} 收：89.95 元
　◦ 夜間訊號：S&P 500 +0.3%、SOX +1.5%，整體偏多
　◦ 今日預判：開盤可能小漲，半導體權值股帶動
・聯發科（2454）
　◦ {last_tw_date} 收：1,450 元
　◦ 夜間訊號：NVDA +2%、AVGO +3%，AI 晶片族群續強
　◦ 今日預判：可望跟漲，留意成交量
・台積電 ADR（TSM 換算）
　◦ ADR {last_us_date} 收 218.5 美元 (+2.8%)，換算理論價約 2,245 元
　◦ vs 台股 {last_tw_date} 收 2,185 元 → 溢價 +2.7%，預估台股開盤跳空高開
）
───────────
🌎 Ch.4 今早焦點（動態挑選）
（從昨夜美股異動最大的個股、財報、總經事件挑 2-3 檔【非持有部位】值得關注，每天動態變動，禁止固定推薦同一批。範例：
・AVGO（博通）— 昨夜 +3.4%
　◦ 為何值得關注：xxx
　◦ 對台股的關聯：xxx
）
───────────
📰 Ch.5 隔夜重要新聞
（挑 3-5 則昨夜美股盤後 / 今晨亞洲盤前最關鍵的新聞，標題用「・」開頭，「這代表什麼」用「　◦ 」）
───────────
💡 Ch.6 今日台股關注點
（基於 ADR 預估開盤方向、可能強勢/弱勢族群、需注意風險，用「・」分點。要明確、可操作）
───────────
⚠️ 本報告由 AI 自動生成，僅供參考，不構成投資建議。

=== 原始資料 ===

【美股昨夜收盤 + 重要指標】
{intl_block}

【美股期貨（盤後延伸）】
{premarket_block}

【美股持有部位】
{us_held_block}

【台股持有部位（{last_tw_date} 收盤價）】
{tw_holdings_block}

【ADR vs 台股昨收（預判開盤方向關鍵）】
{adr_block}

【新聞 RSS（{news_count} 則，台股 + 國際）】
{news_block}
"""


def _latest_date(rows: list[dict], key: str = "as_of") -> str:
    """從資料列表中取最新的 as_of 日期字串，找不到回傳空字串。"""
    dates = [r.get(key, "") for r in rows if r.get(key)]
    return max(dates) if dates else ""


def build_morning_prompt(data: dict[str, Any]) -> str:
    tz = pytz.timezone("Asia/Taipei")
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M (%A)")

    # 自動偵測最近一個美股交易日 & 台股交易日，避免連假後寫錯「昨收」
    last_us_date = _latest_date(data.get("intl", []))
    last_tw_date = _latest_date(data.get("tw_holdings", []))

    date_hint = ""
    if last_us_date:
        date_hint += f"・美股最近交易日：{last_us_date}\n"
    if last_tw_date:
        date_hint += f"・台股最近交易日：{last_tw_date}\n"
    if date_hint:
        date_hint = (
            "【重要】描述收盤時請用「MM/DD 收」或「{date} 收」，"
            "不要寫「昨收」或「昨夜」（可能已隔多日）：\n" + date_hint
        ).format(date=last_tw_date)

    return MORNING_TEMPLATE.format(
        date_str=now,
        date_hint=date_hint,
        last_us_date=last_us_date or "最近交易日",
        last_tw_date=last_tw_date or "最近交易日",
        intl_block=_fmt_intl(data.get("intl", [])),
        premarket_block=_fmt_premarket(data.get("premarket", [])),
        us_held_block=_fmt_us_held(data.get("us_held", [])),
        tw_holdings_block=_fmt_tw_holdings(data.get("tw_holdings", [])),
        adr_block=_fmt_adr(data.get("adr", [])),
        news_count=len(data.get("news", [])),
        news_block=_fmt_news(data.get("news", [])),
    )


@retry(times=3, delay=5.0)
def generate_morning_report(data: dict[str, Any]) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 未設定")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)
    prompt = build_morning_prompt(data)
    logger.info("Gemini 早報 prompt 長度: %d 字元", len(prompt))
    return model.generate_content(prompt).text.strip()


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
