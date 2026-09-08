# 台股加權指數：日線／週線／月線

從 **1967-01-05 至 2026-09-07** 的歷史資料繪圖。內附資料快照，可離線重畫；預設輸出完整歷史月收盤折線圖。互動 HTML 已內嵌資料和 Plotly，開啟後可直接切換日／週／月、收盤折線／K 線、一般／對數刻度，並拖曳日期滑桿。

## 使用

在本資料夾執行（Python 3.10 以上）：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python plot_taiex.py --interval daily
python plot_taiex.py --interval weekly
python plot_taiex.py --interval monthly
```

指定區間與圖形：

```bash
python plot_taiex.py --interval weekly --start 2020-01-01 --end 2026-09-07
python plot_taiex.py --interval monthly --chart candlestick
python plot_taiex.py --interval daily --start 2025-01-01 --output my_daily_chart
```

每次產生 PNG、SVG、HTML；預設名稱為 `taiex_<interval>_<chart>`。HTML 無須安裝 Python 即可使用。CSV 位於 `data/`，包含資料來源、OHLC 是否完整、期間是否結束與實際交易日期。每次執行會更新 `data/taiex_*_bars.csv` 與 `data/audit.json` 為該次指定範圍。

## 週期規則

- `daily`：每個有資料的交易日一筆，保留週六交易。
- `weekly`：週一到週日為一組，涵蓋歷史週六交易；時間軸標示該週最後交易日。
- `monthly`：每個日曆月一組；時間軸標示該月最後交易日。
- K 線：開盤＝首個交易日開盤，最高＝各日最高的最大值，最低＝各日最低的最小值，收盤＝最後交易日收盤。
- 折線：該期間最後交易日收盤，不是期間平均值，也不是移動平均線。
- 先彙整完整期間，再用最後交易日篩選 `--start`；因此開始日期落在週／月中間時，該根 K 棒仍包含該期間起點。`--end` 會截斷最後期間並標記尚未結束。
- 本快照有 16,113 筆日資料、3,090 筆週資料、717 筆月資料；最後一週及 2026 年 9 月尚未結束。

## 來源、取捨與核對

1. **1967 年起的每日收盤彙整**：[011.idv.tw 下載頁](https://www.011.idv.tw/Taiex/FTaiexData.aspx)，[公開 JavaScript 資料檔](https://www.011.idv.tw/Taiex/taiex-Native.js)。本次檔案起於 1967-01-05、止於 2026-03-31，只含收盤價。這是第三方整理，早期及補缺資料未逐筆經官方驗證；「最早」指本次找到並取得的可用歷史紀錄。
2. **證交所日 OHLC**：[發行量加權股價指數歷史資料](https://www.twse.com.tw/zh/indices/taiex/mi-5min-hist.html)，官方該項查詢自 1999-01-05 起提供。已取得 1999-01 至 2002-09，以及 2026-09。擴大下載時遇到 CDN 流量防護，因此本版未宣稱整段都使用官方資料。
3. **Yahoo Finance 日 OHLC**：[^TWII 歷史資料](https://finance.yahoo.com/quote/%5ETWII/history/)，其 API 本次可追溯至 1997-07-02。本程式自 1999 年起使用此來源，凡有同日官方資料皆以官方為準。使用原始價格指數，未做股息再投資或通膨調整，亦未使用 adjusted close。

資料優先順序為 **TWSE > Yahoo Finance（1999 起）> 歷史收盤彙整**。Yahoo 本次缺少部分週六與平日資料，共 26 個 1999 年以後的日期以歷史收盤資料補齊。這些日期的開、高、低仍留空；該週／月只要有一天缺完整 OHLC，就不畫那根 K 棒，改以灰綠收盤點或線表示，避免用收盤資料捏造開高低收。缺日日期完整列在 `data/audit.json` 的 `close_only_dates_since_1999`。

已進行的檢查：

- 原始 JavaScript 含重複分支：31,986 筆數值紀錄合併為 15,999 個日期，同日數值無衝突。只用正規表達式讀取日期／數字，不執行外部 JavaScript。
- 彙整來源與 Yahoo 有 7,038 筆同日可比紀錄，其中 3 筆相差超過 1 點，列於 `data/source_differences.csv`。三筆日期皆有官方資料，最終採官方值。
- 完成补缺後，710 個可比較的完整月，其月底收盤與歷史彙整沒有超過 1 點的差異。此比較含共用來源，只是來源銜接檢查，不代表獨立驗證全部歷史數據。
- 驗證日期唯一且排序、沒有缺整月、價格為正、OHLC 大小關係、週六歸組、跨月週線、未完成期間、缺 OHLC 不產生 K 棒。
- 2026-09-07 的 Yahoo close 為空；已使用官方收盤 **47,326.27** 補齊。2026-08 最後交易日收盤為 **46,128.47**。

每份原始檔的 SHA-256、來源計數與核對摘要保存在 `data/audit.json`；來源網址與快照日期見 `data/raw/manifest.json`。

## 更新資料

```bash
python download_data.py --refresh
python plot_taiex.py --interval monthly
```

下載器需要系統 `curl` 與網路；預設重用原始快取，`--refresh` 才重新取得。`--as-of YYYY-MM-DD` 可指定截止日期。遇到來源限流或錯誤會停止並保留已下載快取，避免默默生成不完整的新快照。網站若改版，可能需要調整下載端點。

不同系統若缺中文字型，可設定 `TAIEX_FONT` 為本機中文字型路徑；macOS 會自動選擇 Arial Unicode，Linux 優先尋找 Noto Sans CJK。
