"""市場代號 —— `market_volume_daily.market` 的合法值。

判讀模型（`services/market_heat.py`）本身跟市場無關：它吃的是「指數收盤 +
當日量能」，每個市場各自用自己的歷史迴歸、自己的近一年分佈排百分位。這裡只
定義有哪些市場，以及各自的資料源起點。
"""

TW = "TW"
"""台股加權指數 + 集中市場成交金額（億元），來源 TWSE FMTQIK。"""

US = "US"
"""Nasdaq Composite 指數 + Nasdaq 上市股票 composite volume（億股）。"""

MARKETS: tuple[str, ...] = (TW, US)
