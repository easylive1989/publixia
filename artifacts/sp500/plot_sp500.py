#!/usr/bin/env python3
"""以 Python 繪製標普 500 日／週／月線，含可離線使用的互動圖。"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/sp500-matplotlib")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager, ticker
from matplotlib.patches import Rectangle
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
LABEL = {"daily": "日", "weekly": "週", "monthly": "月"}
BG, INK, MUTED, TEAL, EARLY, ORANGE = (
    "#f7f5ef", "#203550", "#6a7684", "#315f9b", "#93a7bd", "#b95832")
OHLC = ["open", "high", "low", "close"]
LAUNCH = pd.Timestamp("1957-03-04")
FIRST_OFFICIAL = pd.Timestamp("1928-01-03")


def load_daily(as_of: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    path = RAW / "yahoo_daily.json"
    manifest = json.loads((RAW / "manifest.json").read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != manifest["sha256"]:
        raise ValueError("原始資料與 manifest SHA-256 不符，請確認快照或重新下載")
    payload = json.loads(path.read_text())["chart"]
    if payload.get("error") or not payload.get("result"):
        raise ValueError("Yahoo response error")
    result = payload["result"][0]
    if result["meta"]["symbol"] != "^GSPC":
        raise ValueError("資料不是標普 500 指數")
    days = (pd.to_datetime(result["timestamp"], unit="s", utc=True)
            .tz_convert("America/New_York").normalize().tz_localize(None))
    raw = pd.DataFrame(result["indicators"]["quote"][0], index=days)[OHLC].round(2)
    if not raw.index.is_unique:
        raise ValueError("來源有重複日期")
    excluded = raw.loc[raw.index > as_of]
    daily = raw.loc[:as_of].copy()
    bad_close = ~np.isfinite(daily.close) | (daily.close <= 0)
    dropped_close_dates = [str(d.date()) for d in daily.index[bad_close]]
    daily = daily.loc[~bad_close].copy()
    if daily.empty:
        raise ValueError("指定截止日期之前沒有有效的收盤資料")

    # The historical vendor feed repeats close in all four OHLC fields for the
    # early history and a few later observations. Conservatively use only close.
    flat = daily[OHLC].notna().all(axis=1) & daily[OHLC].nunique(axis=1).eq(1)
    invalid = (~np.isfinite(daily[OHLC]).all(axis=1) | (daily[OHLC] <= 0).any(axis=1)
               | (daily.high < daily[["open", "close"]].max(axis=1))
               | (daily.low > daily[["open", "close"]].min(axis=1)))
    daily["ohlc_quality"] = "vendor_ohlc"
    daily.loc[flat, "ohlc_quality"] = "identical_ohlc_use_close_only"
    daily.loc[invalid, "ohlc_quality"] = "invalid_ohlc_use_close_only"
    daily.loc[flat | invalid, ["open", "high", "low"]] = np.nan
    daily["history_kind"] = np.where(daily.index < FIRST_OFFICIAL, "供應商期初值",
                                     np.where(daily.index < LAUNCH, "推出前回溯", "正式推出後"))
    daily["source"] = "Yahoo Finance ^GSPC"
    daily = daily.sort_index()
    daily.index.name = "date"
    candles = daily.dropna(subset=OHLC)
    assert (candles.high >= candles[["open", "close"]].max(axis=1)).all()
    assert (candles.low <= candles[["open", "close"]].min(axis=1)).all()
    months = daily.index.to_period("M").unique()
    expected = pd.period_range(months.min(), months.max(), freq="M")
    missing_months = expected.difference(months)
    if len(missing_months):
        raise ValueError(f"來源缺少整月：{missing_months.tolist()}")
    # Cleaning OHLC must not alter any available period-end closing price.
    before = raw.loc[:as_of].close.resample("ME").last()
    after = daily.close.resample("ME").last()
    assert before.equals(after)
    audit = {
        "symbol": "^GSPC", "as_of": str(as_of.date()),
        "first_daily_date": str(daily.index.min().date()),
        "last_daily_date": str(daily.index.max().date()), "daily_rows": len(daily),
        "first_ohlc_date": str(candles.index.min().date()) if len(candles) else None,
        "raw_rows": len(raw), "excluded_unfinished_or_after_cutoff_dates": [str(d.date()) for d in excluded.index],
        "dropped_invalid_close_dates": dropped_close_dates,
        "identical_ohlc_rows_treated_as_close_only": int(flat.sum()),
        "invalid_ohlc_rows_treated_as_close_only": int(invalid.sum()),
        "history_kind_counts": daily.history_kind.value_counts().to_dict(),
        "launch_date": str(LAUNCH.date()), "official_first_value_date": str(FIRST_OFFICIAL.date()),
        "missing_months": [], "cleaning_preserves_month_end_close": True,
        "source_url": manifest["url"], "sha256": digest,
        "entire_history_independently_verified": False,
    }
    fred_path = RAW / "fred_recent.csv"
    if fred_path.exists():
        fred_meta = json.loads((RAW / "fred_recent.metadata.json").read_text())
        if hashlib.sha256(fred_path.read_bytes()).hexdigest() != fred_meta["sha256"]:
            raise ValueError("FRED 核對檔 SHA-256 不符")
        fred = pd.read_csv(fred_path, index_col=0, parse_dates=True)["SP500"].dropna()
        comparison = daily.close.to_frame().join(fred.rename("fred"), how="inner")
        comparison["difference"] = (comparison.close - comparison.fred).round(2)
        if len(comparison) and (comparison.difference.abs() > .01).any():
            raise ValueError("近期 Yahoo 與 FRED 收盤值不同，需先核對來源")
        audit["recent_cross_check"] = {
            "source": "FRED SP500", "source_url": fred_meta["url"], "matched_rows": len(comparison),
            "first_date": str(comparison.index.min().date()) if len(comparison) else None,
            "last_date": str(comparison.index.max().date()) if len(comparison) else None,
            "max_absolute_difference": float(comparison.difference.abs().max()) if len(comparison) else None,
        }
        comparison.to_csv(ROOT / "data" / "fred_comparison.csv", float_format="%.2f")
    daily.to_csv(ROOT / "data" / "sp500_daily.csv", float_format="%.2f")
    return daily, audit

def aggregate(daily: pd.DataFrame, interval: str, as_of: pd.Timestamp,
              start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """週＝週一至週日；開取第一日、最高取 max、最低取 min、收取最後日。"""
    freq = {"daily": "D", "weekly": "W-SUN", "monthly": "M"}[interval]
    out = []
    for period, group in daily.groupby(daily.index.to_period(freq), sort=True):
        first, last = group.index[0], group.index[-1]
        # Aggregate the entire calendar period before filtering requested dates.
        # This avoids silently changing the open/high/low when --start is midweek.
        if last < start or last > end:
            continue
        complete_ohlc = group[OHLC].notna().all().all()
        partial_start = bool(first == daily.index.min() and period.start_time < daily.index.min())
        partial_end = bool(period.end_time.normalize() > min(as_of, end))
        reason = "來源起點不足整期" if partial_start else ""
        if partial_end:
            reason = (reason + "；" if reason else "") + "期間尚未結束／已截斷"
        out.append({
            "date": last, "period_start": period.start_time.date().isoformat(),
            "period_end": period.end_time.date().isoformat(),
            "first_trade_date": first.date().isoformat(),
            "last_trade_date": last.date().isoformat(),
            "open": group.open.iloc[0] if complete_ohlc else np.nan,
            "high": group.high.max() if complete_ohlc else np.nan,
            "low": group.low.min() if complete_ohlc else np.nan,
            "close": group.close.iloc[-1], "trading_days": len(group),
            "is_partial": partial_start or partial_end,
            "partial_reason": reason,
            "has_ohlc": bool(complete_ohlc),
            "source": " + ".join(sorted(group.source.unique())),
            "history_kind": " / ".join(dict.fromkeys(group.history_kind)),
        })
    if not out:
        raise ValueError("指定日期範圍沒有資料")
    frame = pd.DataFrame(out).set_index("date")
    assert frame.index.is_unique
    return frame


def configure_fonts() -> None:
    candidates = [os.environ.get("SP500_FONT", ""),
                  "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                  "C:/Windows/Fonts/msjh.ttc"]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            font_manager.fontManager.addfont(candidate)
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=candidate).get_name()
            break
    plt.rcParams.update({"axes.unicode_minus": False, "font.size": 11,
                         "text.color": INK, "axes.labelcolor": MUTED,
                         "xtick.color": MUTED, "ytick.color": MUTED,
                         "svg.fonttype": "path"})


def static_chart(frame: pd.DataFrame, interval: str, chart: str, prefix: Path) -> None:
    configure_fonts()
    label = LABEL[interval]
    kind = "收盤價" if chart == "close" else "K 線"
    fig = plt.figure(figsize=(17, 11), facecolor=BG)
    fig.text(.075, .953, "UNITED STATES  /  EQUITY HISTORY", fontsize=11, color=TEAL, weight="bold")
    fig.text(.075, .909, f"標普 500｜{label}線圖", fontsize=28, weight="bold")
    begin, latest = frame.index.min(), frame.index.max()
    fig.text(.075, .877, f"{begin:%Y.%m.%d} — {latest:%Y.%m.%d}   ·   {len(frame):,} 筆{label}線   ·   {kind}",
             fontsize=12, color=MUTED)
    completed = frame.loc[~frame.is_partial]
    stats = [(f"首筆{label}收盤", f"{frame.close.iloc[0]:,.2f}", f"{begin:%Y.%m.%d}")]
    if not completed.empty:
        stats.append((f"最近完整{label}收盤", f"{completed.close.iloc[-1]:,.2f}", f"{completed.index[-1]:%Y.%m.%d}"))
    stats.append((f"最新{label}收盤" + (" · 尚未結束" if frame.is_partial.iloc[-1] else ""),
                  f"{frame.close.iloc[-1]:,.2f}", f"截至 {latest:%Y.%m.%d}"))
    for i, (caption, value, day) in enumerate(stats):
        left = .075 + i * .29
        fig.text(left, .831, caption, fontsize=10, color=MUTED)
        fig.text(left, .793, value, fontsize=24, weight="bold", color=ORANGE if i == 2 else INK)
        fig.text(left + .145, .796, day, fontsize=10, color=MUTED)
    grid = fig.add_gridspec(2, 1, left=.075, right=.925, top=.728, bottom=.14,
                           height_ratios=[1.3, 1], hspace=.40)
    for panel, scale in enumerate(["log", "linear"]):
        ax = fig.add_subplot(grid[panel], facecolor=BG)
        title = "對數刻度 · 相同比例漲跌，呈現相同高度" if scale == "log" else "一般刻度 · 觀察指數點數變化"
        ax.set_title(title, loc="left", fontsize=12, pad=14, color=INK)
        ax.set_yscale(scale)
        ax.set_axisbelow(True)
        if begin < LAUNCH:
            ax.axvspan(begin, min(LAUNCH, latest), color=EARLY, alpha=.14, zorder=0)
        if begin < LAUNCH < latest:
            ax.axvline(LAUNCH, color=MUTED, ls=(0, (3, 4)), lw=.8)
            ax.text(LAUNCH + pd.Timedelta(days=300), .965, "1957.03 正式推出",
                    transform=ax.get_xaxis_transform(), color=MUTED, fontsize=9, va="top")
        ax.grid(axis="y", color="#dce2da", linewidth=.65)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(axis="both", which="both", length=0, pad=9)
        ax.yaxis.tick_right()
        if chart == "close":
            ax.plot(frame.index, frame.close, color=TEAL, lw=1.5 if interval == "monthly" else .85)
            if scale == "linear":
                ax.fill_between(frame.index, frame.close, color=TEAL, alpha=.07)
        else:
            fallback = frame.close.where(~frame.has_ohlc)
            ax.plot(frame.index, fallback, color=EARLY, lw=1.1, marker=".", markersize=2)
            width = {"daily": .65, "weekly": 4.5, "monthly": 20}[interval]
            for day, row in frame.loc[frame.has_ohlc].iterrows():
                x = mdates.date2num(day)
                color = "#c15d50" if row.close >= row.open else TEAL
                ax.vlines(x, row.low, row.high, color=color, linewidth=.55)
                if row.open == row.close:
                    ax.hlines(row.close, x - width / 2, x + width / 2, color=color, linewidth=.6)
                else:
                    ax.add_patch(Rectangle((x - width / 2, min(row.open, row.close)),
                                           width, abs(row.close - row.open),
                                           facecolor=color, edgecolor=color, linewidth=.4))
        if frame.is_partial.iloc[-1]:
            ax.scatter([latest], [frame.close.iloc[-1]], s=27, color=ORANGE,
                       marker="D", zorder=5, edgecolors=BG, linewidth=.7)
        span = max((latest - begin).days, 30)
        ax.set_xlim(begin - pd.Timedelta(days=span * .012), latest + pd.Timedelta(days=span * .025))
        if span > 3650:
            ax.xaxis.set_major_locator(mdates.YearLocator(10 if span > 25000 else 5))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        else:
            locator = mdates.AutoDateLocator(minticks=4, maxticks=10)
            ax.xaxis.set_major_locator(locator)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        if scale == "log":
            lo = frame.low.min() if chart == "candlestick" else frame.close.min()
            lo = min(float(lo) if pd.notna(lo) else frame.close.min(), frame.close.min())
            candidate_hi = frame.high.max() if chart == "candlestick" else frame.close.max()
            hi = max(float(candidate_hi) if pd.notna(candidate_hi) else frame.close.max(), frame.close.max())
            ticks = [v * 10 ** p for p in range(0, 6) for v in [1, 2, 5]
                     if lo * .9 <= v * 10 ** p <= hi * 1.2]
            ax.set_ylim(lo * .82, hi * 1.35)
            ax.yaxis.set_major_locator(ticker.FixedLocator(ticks))
            ax.yaxis.set_major_formatter(ticker.StrMethodFormatter("{x:,.0f}"))
            ax.yaxis.set_minor_locator(ticker.NullLocator())
        else:
            ax.set_ylim(bottom=0)
            ax.yaxis.set_major_locator(ticker.MaxNLocator(5))
            ax.yaxis.set_major_formatter(ticker.StrMethodFormatter("{x:,.0f}"))
        if span > 15000 and chart == "close" and scale == "log":
            events = [("1929", "1929 年月收盤高點", "max", (-30, 24)),
                      ("1932", "1932 年月收盤低點", "min", (35, 65)),
                      ("2000", "2000 年月收盤高點", "max", (-100, 22)),
                      ("2009", "2009 年月收盤低點", "min", (18, -33))]
            if interval == "monthly":
                for year, text, fn, offset in events:
                    subset = frame.loc[frame.index.year == int(year)]
                    if not subset.empty:
                        day = subset.close.idxmax() if fn == "max" else subset.close.idxmin()
                        value = subset.loc[day, "close"]
                        ax.scatter([day], [value], s=16, color=TEAL, zorder=4)
                        ax.annotate(f"{text}\n{value:,.2f}", (day, value), xytext=offset,
                                    textcoords="offset points", fontsize=9, color=INK,
                                    arrowprops={"arrowstyle": "-", "color": MUTED, "lw": .6})
    foot = "來源：Yahoo Finance ^GSPC。1957-03-04 正式推出；之前屬回溯資料。1927 年末為供應商期初值。"
    fig.text(.075, .083, foot, fontsize=9, color=MUTED)
    note = ("月線＝每月最後可用收盤；週線＝週一至週日彙整。價格指數，未含股息再投資。"
            if chart == "close" else "開高低收相同或不完整的期間以灰藍點／線呈現；K 線紅漲藍跌。未含股息再投資。")
    fig.text(.075, .059, note, fontsize=9, color=MUTED)
    if frame.is_partial.iloc[-1]:
        fig.text(.075, .035, f"◆ 最後一筆{label}線尚未結束，截至 {latest:%Y-%m-%d}；已排除盤中交易日。", fontsize=9, color=ORANGE)
    else:
        fig.text(.075, .035, "只使用已收盤交易日；資料來源與清理說明詳見 README / audit.json。", fontsize=9, color=MUTED)
    fig.savefig(prefix.with_suffix(".png"), dpi=180, facecolor=BG)
    fig.savefig(prefix.with_suffix(".svg"), facecolor=BG)
    plt.close(fig)


def interactive_chart(frames: dict, interval: str, chart: str, prefix: Path) -> None:
    fig = go.Figure()
    buttons = []
    ordered = list(LABEL)
    total_traces = 3 * len(ordered)
    initial = ordered.index(interval) * 3
    for i, (freq, frame) in enumerate(frames.items()):
        label = LABEL[freq]
        dates = frame.index.strftime("%Y-%m-%d").tolist()
        status = [reason or "完整期間" for reason in frame.partial_reason]
        custom = np.column_stack([frame.source, frame.first_trade_date, frame.last_trade_date, status, frame.history_kind])
        fig.add_trace(go.Scatter(x=dates, y=frame.close.tolist(), name=f"{label}收盤價", mode="lines",
                                line={"color": TEAL, "width": 1.5}, customdata=custom,
                                hovertemplate="%{x}<br>收盤 %{y:,.2f}<br>%{customdata[3]}<br>%{customdata[4]}<br>%{customdata[0]}<extra></extra>",
                                visible=i * 3 == initial and chart == "close"))
        fallback = [float(r.close) if not r.has_ohlc else None for _, r in frame.iterrows()]
        fig.add_trace(go.Scatter(x=dates, y=fallback, connectgaps=False, mode="lines+markers", marker={"size": 3},
                                name="僅有收盤價的期間", line={"color": EARLY, "width": 1.3},
                                hovertemplate="%{x}<br>收盤 %{y:,.2f}<br>此期間無完整開高低收<extra></extra>",
                                visible=i * 3 == initial and chart == "candlestick"))
        candles = frame.loc[frame.has_ohlc]
        fig.add_trace(go.Candlestick(x=candles.index.strftime("%Y-%m-%d").tolist(),
                                    open=candles.open.tolist(), high=candles.high.tolist(),
                                    low=candles.low.tolist(), close=candles.close.tolist(), name=f"{label} K 線",
                                    increasing={"line": {"color": "#c15d50"}, "fillcolor": "#c15d50"},
                                    decreasing={"line": {"color": TEAL}, "fillcolor": TEAL},
                                    text=[f"{r.source}；{r.partial_reason or '完整期間'}；{r.history_kind}" for _, r in candles.iterrows()],
                                    visible=i * 3 == initial and chart == "candlestick"))
        for kind in ["close", "candlestick"]:
            visible = [False] * total_traces
            if kind == "close":
                visible[i * 3] = True
            else:
                visible[i * 3 + 1] = visible[i * 3 + 2] = True
            text = f"{label}線 · " + ("收盤折線" if kind == "close" else "K 線")
            buttons.append({"label": text, "method": "update", "args": [
                {"visible": visible}, {"title.text": f"標普 500｜{text}"}]})
    label = LABEL[interval]
    last = frames[interval].index.max().strftime("%Y-%m-%d")
    first = frames[interval].index.min()
    if first < LAUNCH:
        fig.add_vrect(x0=first.strftime("%Y-%m-%d"), x1=min(LAUNCH, frames[interval].index.max()).strftime("%Y-%m-%d"),
                      fillcolor=EARLY, opacity=.14, line_width=0, layer="below")
    if first < LAUNCH < frames[interval].index.max():
        fig.add_shape(type="line", x0="1957-03-04", x1="1957-03-04", y0=0, y1=1,
                      xref="x", yref="paper", line={"color": MUTED, "width": 1, "dash": "dot"})
        fig.add_annotation(x="1957-03-04", y=.97, xref="x", yref="paper", text="1957.03 正式推出",
                           showarrow=False, xanchor="left", xshift=7, font={"color": MUTED, "size": 11})
    fig.update_layout(
        title={"text": f"標普 500｜{label}線 · " + ("收盤折線" if chart == "close" else "K 線"),
               "x": .035, "y": .985, "yanchor": "top", "font": {"size": 23}},
        paper_bgcolor=BG, plot_bgcolor=BG, font={"family": "Arial, PingFang TC, sans-serif", "color": INK},
        height=760, margin={"l": 45, "r": 90, "t": 140, "b": 60}, showlegend=False,
        yaxis={"type": "log", "side": "right", "tickformat": ",.0f", "gridcolor": "#dce2da", "title": "指數點數"},
        xaxis={"type": "date", "rangeslider": {"visible": True, "thickness": .13},
               "rangeselector": {"buttons": [
                   {"count": 1, "label": "1 年", "step": "year", "stepmode": "backward"},
                   {"count": 5, "label": "5 年", "step": "year", "stepmode": "backward"},
                   {"count": 10, "label": "10 年", "step": "year", "stepmode": "backward"},
                   {"step": "all", "label": "全部"}]}},
        updatemenus=[
            {"buttons": buttons, "active": initial // 3 * 2 + (chart == "candlestick"), "x": .01, "y": 1.20, "xanchor": "left"},
            {"type": "buttons", "direction": "right", "x": .39, "y": 1.20, "xanchor": "left", "buttons": [
                {"label": "對數刻度", "method": "relayout", "args": [{"yaxis.type": "log", "yaxis.autorange": True}]},
                {"label": "一般刻度", "method": "relayout", "args": [{"yaxis.type": "linear", "yaxis.autorange": True}]}]},
        ],
    )
    html = fig.to_html(full_html=True, include_plotlyjs=True,
                       config={"responsive": True, "scrollZoom": True, "displaylogo": False,
                               "toImageButtonOptions": {"format": "png", "filename": prefix.name, "scale": 2}})
    notes = f'''<div style="max-width:1200px;margin:0 auto 24px;padding:0 30px;color:{MUTED};font:14px/1.8 Arial,sans-serif">
資料截至 <strong>{last}</strong>。下拉選單可切換日／週／月線與 K 線；下方滑桿可調整日期範圍。<br>
週線按週一至週日、月線按日曆月彙整；時間軸標示最後交易日。尚未結束的週／月是暫定數據。<br>
1957-03-04 正式推出 S&amp;P 500；灰色區域為推出前回溯資料，1927 年末為 Yahoo 提供的期初值。<br>
早期開高低收相同的紀錄保守視為只有收盤價；不產生 K 棒。未含股息再投資，已排除尚未收盤的交易日。<br>
来源：<a href="https://finance.yahoo.com/quote/%5EGSPC/history/">Yahoo Finance ^GSPC</a>；
指數沿革：<a href="https://www.spglobal.com/spdji/en/indices/equity/sp-500/?os=io___">S&amp;P Dow Jones Indices</a>。
</div>'''
    html = html.replace("<head>", '<head><meta name="viewport" content="width=device-width, initial-scale=1"><title>標普 500歷史線圖</title>')
    html = html.replace("<body>", f'<body style="margin:0;background:{BG}">')
    html = html.replace("</body>", notes + "</body>")
    prefix.with_suffix(".html").write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", choices=list(LABEL), default="monthly", help="daily 日線 / weekly 週線 / monthly 月線")
    parser.add_argument("--chart", choices=["close", "candlestick"], default="close", help="收盤折線或 K 線")
    parser.add_argument("--start", type=date.fromisoformat, default=date(1927, 12, 30))
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--output", type=Path, help="輸出檔案前綴（不含副檔名）")
    args = parser.parse_args()
    manifest = json.loads((RAW / "manifest.json").read_text())
    as_of = pd.Timestamp(manifest["as_of"])
    end = min(pd.Timestamp(args.end) if args.end else as_of, as_of)
    start = pd.Timestamp(args.start)
    if start > end:
        parser.error("--start 不可晚於 --end／資料快照日期")
    daily, audit = load_daily(as_of)
    # --end can deliberately truncate the last period. Keep full periods at the
    # left edge, but aggregate only available days through the requested end.
    daily = daily.loc[:end]
    frames = {interval: aggregate(daily, interval, as_of, start, end) for interval in LABEL}
    for interval, frame in frames.items():
        frame.to_csv(ROOT / "data" / f"sp500_{interval}_bars.csv", float_format="%.2f")
    frame = frames[args.interval]
    prefix = args.output or ROOT / f"sp500_{args.interval}_{args.chart}"
    prefix.parent.mkdir(parents=True, exist_ok=True)
    static_chart(frame, args.interval, args.chart, prefix)
    interactive_chart(frames, args.interval, args.chart, prefix)
    audit.update({"interval": args.interval, "chart": args.chart, "selected_rows": len(frame),
                  "bars_by_interval": {k: len(v) for k, v in frames.items()},
                  "last_selected_close": float(frame.close.iloc[-1]),
                  "last_period_is_partial": bool(frame.is_partial.iloc[-1])})
    (ROOT / "data" / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: audit[k] for k in ["first_daily_date", "last_daily_date", "daily_rows", "bars_by_interval", "last_selected_close", "last_period_is_partial"]}, ensure_ascii=False, indent=2))
    print(f"已輸出：{prefix}.png / .svg / .html")


if __name__ == "__main__":
    main()
