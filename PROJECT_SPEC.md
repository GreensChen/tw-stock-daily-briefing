# 台股日報系統 — 專案規格書

## 專案名稱
`tw-stock-daily`

## 目標
每天台灣時間 20:30，自動生成一份台股日報，透過 LINE Messaging API 推送到我的手機。

## 風格定位
參考「游庭皓的財經皓角」的表達方式：
- 用總經框架串連國際局勢和台股
- 不只堆數據，要有「所以呢？」的觀點判讀
- 從宏觀到微觀：國際 → 大盤 → 個股
- 語氣專業但不生硬，像在跟朋友聊市場

## 報告結構

### Ch.1 🌍 國際市場總覽
- 美股四大指數（道瓊、S&P 500、NASDAQ、費城半導體）
- 關鍵指標：美國 10 年期公債殖利率、美元指數 DXY、VIX、WTI 原油、黃金
- 宏觀判讀：這些數據組合起來代表什麼？對台股的影響？
- Fed 動態 / 地緣政治 / 重要總經數據

### Ch.2 📊 台股大盤
- 加權指數、櫃買指數、成交量
- 三大法人買賣超（外資、投信、自營商）+ 近五日累計
- 強弱類股排行
- 盤勢判讀

### Ch.3 🔍 觀察清單個股
目前追蹤：
- **0050** 元大台灣50
- **0056** 元大高股息
- **2330** 台積電

每檔呈現：
- 今日行情（開高低收、成交量）
- 三大法人買賣超
- 近期基本面動態（月營收、EPS、法說會摘要）
- 觀察重點

### Ch.4 📰 今日重要新聞
- 3-5 則影響市場的關鍵新聞
- 每則附簡評（這件事代表什麼、對哪些股票有影響）

### Ch.5 💡 明日觀察重點
- 國際面：即將公布的經濟數據、財報、事件
- 台股面：技術面關鍵位置、法人動向、需注意的風險

## 資料來源

### 台股數據（免費）
- **TWSE OpenAPI**：加權指數、個股行情、三大法人買賣超
  - 每日收盤行情：https://www.twse.com.tw/exchangeReport/MI_INDEX
  - 三大法人：https://www.twse.com.tw/fund/BFI82U
  - 個股法人進出：https://www.twse.com.tw/fund/T86
- **TPEX**（櫃買中心）：櫃買指數
  - https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_index/st41.php

### 國際數據（免費）
- **yfinance**：美股指數、美債殖利率、美元指數、原油、黃金、VIX
  - ^DJI, ^GSPC, ^IXIC, ^SOX（美股四大指數）
  - ^TNX（10年期美債殖利率）
  - DX-Y.NYB（美元指數）
  - ^VIX（恐慌指數）
  - CL=F（WTI 原油）
  - GC=F（黃金）

### 新聞（免費）
- RSS feed 抓取：
  - 鉅亨網：https://news.cnyes.com/news/cat/tw_stock（需確認 RSS 可用性）
  - 經濟日報：https://money.udn.com/rssfeed/news/1001/5590
  - MoneyDJ：https://www.moneydj.com/rss/rssfeed.aspx
- 公開資訊觀測站（重大訊息）：https://mops.twse.com.tw

### AI 分析
- **Gemini 2.5 Flash API**（Google AI Studio）
  - 用來把原始數據 + 新聞 → 生成有觀點的報告
  - Model: `gemini-2.5-flash-preview-04-17`（或最新穩定版）

### 通知
- **LINE Messaging API**
  - Push Message 到我的 LINE

## 技術架構

```
crontab（每天 20:30 TST）
  ↓
main.py
  ├── data/fetcher_twse.py     # 抓台股數據
  ├── data/fetcher_intl.py     # 抓國際數據（yfinance）
  ├── data/fetcher_news.py     # 抓新聞 RSS
  ├── report/generator.py      # 用 Gemini Flash 生成報告
  ├── notify/line_bot.py       # LINE 推送
  └── config.py                # 設定檔（股票清單、API keys）
```

## 設定檔結構

```python
# config.py
WATCHLIST = [
    {"code": "0050", "name": "元大台灣50", "type": "etf"},
    {"code": "0056", "name": "元大高股息", "type": "etf"},
    {"code": "2330", "name": "台積電", "type": "stock"},
]

# 環境變數
# GEMINI_API_KEY
# LINE_CHANNEL_ACCESS_TOKEN
# LINE_USER_ID
```

## 部署環境
- **伺服器**：Hetzner Cloud VPS（最小方案，Ubuntu，新加坡機房）
- **Python 3.11+**
- **crontab**：`30 20 * * 1-5 /path/to/run.sh`（週一到週五）

## LINE 訊息格式
- 使用 Flex Message 或純文字（先用純文字，之後可升級 Flex Message）
- LINE 單則訊息有 5000 字元限制，如果報告太長要拆成多則
- 用 emoji 和分隔線增加可讀性

## 未來擴充（先不做）
- [ ] 觀察清單動態增減（透過 LINE 指令）
- [ ] YouTube 訂閱頻道每日新片通知
- [ ] 週報 / 月報彙整
- [ ] 法說會逐字稿自動翻譯（接 yt2epub）
- [ ] Flex Message 美化
- [ ] 歷史報告歸檔和查詢

## 注意事項
- 台股只有週一到週五開盤，週末和國定假日不需要跑
- TWSE API 有時會延遲或格式改變，要做好 error handling
- Gemini API 的 prompt 要明確要求繁體中文、財經皓角風格
- 報告結尾加上免責聲明：「本報告由 AI 自動生成，僅供參考，不構成投資建議。」
- API keys 用環境變數管理，不要寫死在程式碼裡
