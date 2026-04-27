"""LINE Messaging API push（直接打 REST，不依賴 SDK）"""
from __future__ import annotations

import logging
import os

import requests

from config import LINE_MAX_CHARS

logger = logging.getLogger(__name__)

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def _split_message(text: str, max_chars: int = LINE_MAX_CHARS) -> list[str]:
    """超過 LINE 5000 字限制要拆訊息。優先在「分隔線」處切，避免切到字。"""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > max_chars:
        cut = remaining.rfind("───────────", 0, max_chars)
        if cut == -1:
            cut = remaining.rfind("\n\n", 0, max_chars)
        if cut == -1:
            cut = remaining.rfind("\n", 0, max_chars)
        if cut == -1 or cut < max_chars // 2:
            cut = max_chars
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def push_text(text: str, user_id: str | None = None, token: str | None = None) -> None:
    """推送（自動拆訊息）。LINE push 一次最多 5 則 message。"""
    token = token or os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = user_id or os.environ.get("LINE_USER_ID")
    if not token or not user_id:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN / LINE_USER_ID 未設定")

    chunks = _split_message(text)
    logger.info("LINE 拆成 %d 則訊息（總長 %d 字）", len(chunks), len(text))

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # LINE 一次 push 最多 5 個 message → 超過要分批 push
    for i in range(0, len(chunks), 5):
        batch = chunks[i:i+5]
        payload = {
            "to": user_id,
            "messages": [{"type": "text", "text": c} for c in batch],
        }
        resp = requests.post(LINE_PUSH_URL, headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            logger.error("LINE push 失敗 %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()
    logger.info("LINE push 成功")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    push_text("✅ 台股日報系統測試訊息\n如果你看到這則，表示 LINE 推送已串接成功。")
