"""LINE Messaging API push（直接打 REST，不依賴 SDK）

多人推送設定方式：
  - 單人：.env 設 LINE_USER_ID=Uxxxx
  - 多人：.env 設 LINE_USER_IDS=Uxxxx,Uyyy,Uzzz（逗號分隔，最多 500 人）
  若兩個都設，以 LINE_USER_IDS 為主。
"""
from __future__ import annotations

import logging
import os

import requests

from config import LINE_MAX_CHARS
from utils import retry

logger = logging.getLogger(__name__)

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_MULTICAST_URL = "https://api.line.me/v2/bot/message/multicast"


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


def _get_user_ids() -> list[str]:
    """從環境變數讀取收件人清單。LINE_USER_IDS 優先（多人），否則 fallback 到 LINE_USER_ID。"""
    multi = os.environ.get("LINE_USER_IDS", "").strip()
    if multi:
        ids = [uid.strip() for uid in multi.split(",") if uid.strip()]
        if ids:
            return ids
    single = os.environ.get("LINE_USER_ID", "").strip()
    if single:
        return [single]
    return []


@retry(times=3, delay=3.0)
def push_text(text: str, user_ids: list[str] | None = None, token: str | None = None) -> None:
    """推送給一人或多人（自動拆訊息）。

    Args:
        text: 要推送的文字
        user_ids: 指定收件人清單；若為 None，從環境變數讀取
        token: LINE Channel Access Token；若為 None，從環境變數讀取
    """
    token = token or os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN 未設定")

    if user_ids is None:
        user_ids = _get_user_ids()
    if not user_ids:
        raise RuntimeError("找不到收件人：請設定 LINE_USER_IDS 或 LINE_USER_ID")

    chunks = _split_message(text)
    logger.info("LINE 拆成 %d 則訊息（總長 %d 字），收件人 %d 位", len(chunks), len(text), len(user_ids))

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    if len(user_ids) == 1:
        # 單人：用 push（相容舊行為）
        _push_single(chunks, user_ids[0], headers)
    else:
        # 多人：用 multicast（LINE 一次最多 500 人，messages 最多 5 則）
        _push_multicast(chunks, user_ids, headers)

    logger.info("LINE 推送成功")


def _push_single(chunks: list[str], user_id: str, headers: dict) -> None:
    """單人 push，每批最多 5 則。"""
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


def _push_multicast(chunks: list[str], user_ids: list[str], headers: dict) -> None:
    """多人 multicast，每批最多 5 則 message，收件人最多 500。"""
    # multicast 每次最多 500 人
    for uid_start in range(0, len(user_ids), 500):
        batch_ids = user_ids[uid_start:uid_start+500]
        for i in range(0, len(chunks), 5):
            batch_msgs = chunks[i:i+5]
            payload = {
                "to": batch_ids,
                "messages": [{"type": "text", "text": c} for c in batch_msgs],
            }
            resp = requests.post(LINE_MULTICAST_URL, headers=headers, json=payload, timeout=15)
            if resp.status_code != 200:
                logger.error("LINE multicast 失敗 %s: %s", resp.status_code, resp.text)
                resp.raise_for_status()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    push_text("✅ 台股日報系統測試訊息\n如果你看到這則，表示 LINE 推送已串接成功。")
