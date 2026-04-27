"""全域設定：觀察清單、國際指標代碼、新聞來源"""

WATCHLIST = [
    {"code": "0050", "name": "元大台灣50", "type": "etf"},
    {"code": "0056", "name": "元大高股息", "type": "etf"},
    {"code": "2330", "name": "台積電", "type": "stock"},
]

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
