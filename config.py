"""全域設定：觀察清單、國際指標代碼、新聞來源"""

WATCHLIST = [
    {"code": "0050", "name": "元大台灣50", "type": "etf"},
    {"code": "006208", "name": "富邦台50", "type": "etf"},
    {"code": "00895", "name": "富邦未來車", "type": "etf"},
    {"code": "2330", "name": "台積電", "type": "stock"},
    {"code": "2454", "name": "聯發科", "type": "stock"},
]

# 美股持有部位
US_HELD = [
    {"ticker": "QQQ", "name": "Invesco QQQ (NASDAQ 100)"},
    {"ticker": "SPY", "name": "SPDR S&P 500"},
    {"ticker": "NVDA", "name": "輝達 NVIDIA"},
]

# 美股外部機會 = 動態，由 Gemini 從當天新聞 + 市場動向挑出，不寫死

# === 早報專用 ===

# 台股 ADR：用來預判台股開盤方向
# ratio: 1 ADR 對應幾股 TW 普通股
ADR_TICKERS = [
    {"adr": "TSM",  "name": "台積電 ADR", "tw_code": "2330.TW", "tw_name": "台積電",   "ratio": 5},
    {"adr": "UMC",  "name": "聯電 ADR",   "tw_code": "2303.TW", "tw_name": "聯電",     "ratio": 5},
    {"adr": "ASX",  "name": "日月光 ADR", "tw_code": "3711.TW", "tw_name": "日月光投控", "ratio": 2},
]

# 美股期貨（早報時可參考的盤前/盤後延伸訊號）
PREMARKET_TICKERS = {
    "ES=F": "S&P 500 期貨",
    "NQ=F": "NASDAQ 期貨",
    "YM=F": "道瓊期貨",
}

INTL_TICKERS = {
    "^DJI": "道瓊工業指數",
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ",
    "^SOX": "費城半導體",
    "^TNX": "美國10年期公債殖利率",
    "DX-Y.NYB": "美元指數 DXY",
    "^VIX": "VIX 恐慌指數",
    "CL=F": "WTI 原油",
    "GC=F": "黃金",
}

NEWS_FEEDS = [
    {"name": "經濟日報", "url": "https://money.udn.com/rssfeed/news/1001/5590"},
    {"name": "鉅亨網台股", "url": "https://news.cnyes.com/rss/cat/tw_stock"},
]

GEMINI_MODEL = "gemini-2.5-flash"

LINE_MAX_CHARS = 4800  # 留 buffer，LINE 上限 5000
