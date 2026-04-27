# CLAUDE.md — Claude Code 開發指引

## 專案概述
這是一個台股每日報告自動化系統。每天台灣時間 20:30 自動抓取台股和國際市場數據，用 Gemini Flash API 生成有觀點的分析報告，透過 LINE Messaging API 推送到手機。

## 開發優先順序
請按以下順序開發，每完成一步先確認能跑再往下：

### Phase 1：資料抓取
1. `data/fetcher_twse.py` — 抓台股收盤行情、三大法人買賣超、個股資料
2. `data/fetcher_intl.py` — 用 yfinance 抓美股、美債、美元、VIX、原油、黃金
3. `data/fetcher_news.py` — 抓新聞 RSS feed
4. 寫測試確認每個 fetcher 都能正確取得資料

### Phase 2：報告生成
5. `report/generator.py` — 把所有資料組成 prompt，呼叫 Gemini Flash 生成報告
6. prompt 要明確指定風格（參考 PROJECT_SPEC.md 中的風格定位）

### Phase 3：LINE 推送
7. `notify/line_bot.py` — 用 LINE Messaging API 推送報告
8. 處理訊息長度限制（超過 5000 字要拆成多則）

### Phase 4：整合
9. `main.py` — 串接所有步驟
10. `run.sh` — crontab 用的啟動腳本
11. 錯誤處理和 logging

## 技術規範
- Python 3.11+
- 使用 `requests` 做 HTTP 呼叫（不要用 aiohttp，保持簡單）
- yfinance 抓國際數據
- Gemini API 用 `google-generativeai` SDK
- LINE 用 `line-bot-sdk` 或直接打 REST API
- API keys 全部用環境變數（`os.environ`）
- 加上 `requirements.txt`
- 加上 `.env.example` 列出需要的環境變數

## 重要注意
- TWSE API 回傳格式可能是 JSON 或 CSV，要做好解析
- TWSE 有時會回傳 HTML 錯誤頁面，要檢查 response content-type
- 台股只有週一到週五開盤
- 所有時間用台灣時區（Asia/Taipei）
- Gemini prompt 要用繁體中文
- 報告結尾固定加免責聲明

## 檔案結構
```
tw-stock-daily/
├── CLAUDE.md              # 本檔案
├── PROJECT_SPEC.md        # 完整規格書
├── requirements.txt
├── .env.example
├── config.py              # 設定檔（股票清單等）
├── main.py                # 主程式入口
├── run.sh                 # crontab 啟動腳本
├── data/
│   ├── __init__.py
│   ├── fetcher_twse.py    # 台股數據
│   ├── fetcher_intl.py    # 國際數據
│   └── fetcher_news.py    # 新聞
├── report/
│   ├── __init__.py
│   └── generator.py       # Gemini 報告生成
├── notify/
│   ├── __init__.py
│   └── line_bot.py        # LINE 推送
└── logs/                  # 日誌資料夾
```
