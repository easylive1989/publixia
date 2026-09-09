# 標普 500：日線／週線／月線

以 Python 繪製 S&P 500（Yahoo 代碼 `^GSPC`）歷史收盤折線與 K 線，沿用台股圖表的使用方式。預設月線圖同時提供一般刻度與對數刻度；互動 HTML 可切換日／週／月、折線／K 線、座標刻度與日期範圍，已內嵌資料及 Plotly，可離線開啟。

本次已收盤資料範圍：**1927-12-30 至 2026-09-08（紐約交易日期）**。

## 使用

Python 3.10 以上，在本資料夾執行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python plot_sp500.py --interval daily
python plot_sp500.py --interval weekly
python plot_sp500.py --interval monthly
```

日期範圍與 K 線：

```bash
python plot_sp500.py --interval weekly --start 2000-01-01 --end 2026-09-08
python plot_sp500.py --interval monthly --chart candlestick
python plot_sp500.py --interval daily --start 2025-01-01 --output my_sp500_chart
```

每次產生 `sp500_<interval>_<chart>.png`、`.svg`、`.html`；`--output` 可指定不含副檔名的前綴。`data/` 保存清理後日資料、三種週期 CSV、資料品質及來源核對紀錄。週期 CSV 和 `audit.json` 會更新為當次指定範圍。內附預先產生的日／週／月圖片與月 K 圖，`sp500_monthly_close.html` 包含全部六種切換模式。

## 日期與彙整

- 日線：每個有資料且已收盤的紐約交易日一筆，不補休市日，也不以盤中報價充當收盤價。
- 週線：週一至週日彙整；月線：按日曆月彙整。折線取該期間最後可用收盤價；時間軸顯示最後一筆資料的交易日期。
- K 線：開盤取首日開盤，最高取各日最高的最大值，最低取各日最低的最小值，收盤取最後一日收盤。
- `--start` 按彙整後最後交易日篩選，保留該週／月起點，避免中途起算導致開盤價改變。`--end` 可截斷最後一期。
- 不足整期的來源起點及尚未結束／被截斷的期間會標記 `is_partial`，並附 `partial_reason`。
- 2026-09-09 的資料下載時美股尚未收盤，已排除；本次最新收盤為 **2026-09-08，7,673.52**。2026 年 9 月及最後一週仍為未完成期間。

## 歷史定義與資料品質

依 [S&P Dow Jones Indices 的指數說明](https://www.spglobal.com/spdji/en/indices/equity/sp-500/?os=io___)，S&P 500 於 **1957-03-04 正式推出**，官方列示最早指數值日期為 **1928-01-03**；推出前的績效屬回溯資料。圖中以灰藍底色和垂直虛線區分推出前後。

Yahoo 此次額外提供 **1927-12-30 的 17.66 點**，本版保留為供應商期初值，沒有宣稱那是當時正式發布的 500 檔股票指數。更早的學術長期股價序列可能使用不同指數、月平均值或重建方法，本版不將它们混接進這套日／週／月資料。

來源為 [Yahoo Finance ^GSPC 歷史資料](https://finance.yahoo.com/quote/%5EGSPC/history/)。本圖是名目價格指數，未包含股息再投資、通膨調整或台幣匯率；不是 SPY ETF，也未使用 adjusted close。

來源早期將開、高、低、收全部填成相同值。程式保守地只保留這些紀錄的收盤價，其餘欄位設為空值，避免畫出無法驗證的 K 棒；完整日內價格範圍最早出現在 **1962-01-02**。少數後期相同值紀錄也採相同規則。週／月只要任一天缺完整 OHLC，就以灰藍收盤點／線呈現該期，不產生 K 棒；後續缺值之間不連線。

## 本次核對

- 原始來源 24,789 筆，排除當日盤中紀錄後為 **24,788 筆日資料、5,150 筆週資料、1,186 筆月資料**。
- 日期唯一、排序正確，沒有缺整月。所有有效收盤值為正；OHLC 清理沒有改變任何月末收盤值。
- **8,547 筆**開高低收相同的紀錄改以收盤價使用；完整日 K 共 16,241 筆，完整週 K 共 3,359 筆，完整月 K 共 765 筆。
- 以 [FRED SP500](https://fred.stlouisfed.org/series/SP500) 交叉核對 **2026-08-03 至 2026-09-08 的 26 筆收盤資料**，差異皆為 0.00 點。此為近期分發來源之間的核對，不代表全部歷史已逐筆獨立驗證。比對結果見 `data/fred_comparison.csv`。
- 原始 Yahoo／FRED 檔、取得日期、URL 與 SHA-256 均保留在 `data/raw/`；程式會檢查檔案雜湊。完整處理摘要見 `data/audit.json`。
- 已檢查日／週／月彙整、跨月週線、缺 OHLC、第一期不足整期、1957 年分界與盤中資料排除；瀏覽器已測試六種切換模式及標題排版。

## 更新

```bash
python download_data.py --refresh
python plot_sp500.py --interval monthly
```

下載器使用系統 `curl`，無須 API 金鑰；預設重用快照，`--refresh` 才更新。`--as-of YYYY-MM-DD` 以紐約日期指定歷史截止日期；以來源交易時段資訊排除尚未結束的當日。若無交易時段資訊，保守排除今日。

FRED 核對檔保留本次固定期間，更新 Yahoo 不會擴充 FRED 核對範圍。若兩個來源在已有重疊日期出現差異，程式會停止並提示先核對。第三方下載端點可能限流或改版。

中文字型可透過 `SP500_FONT` 指定；macOS 自動尋找 Arial Unicode，Linux 尋找 Noto Sans CJK。
