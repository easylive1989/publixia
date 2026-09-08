#!/usr/bin/env python3
"""以 Python 畫台股加權指數日線、週線、月線；支援收盤折線與 K 線。"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re

os.environ.setdefault("MPLCONFIGDIR", "/tmp/taiex-matplotlib")
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
    "#f7f5ef", "#183a38", "#667671", "#147769", "#91a99c", "#b95832")
OHLC = ["open", "high", "low", "close"]


def load_daily(as_of: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    raw = (RAW / "archive_daily.js").read_text(encoding="utf-8-sig")
    # The downloaded archive has duplicated merge-conflict branches. Parse only
    # numeric literals, reject conflicting duplicates, and NEVER eval JavaScript.
    pairs = re.findall(r"\[new Date\('([0-9/]+)'\),([0-9.]+)\]", raw)
    values = {}
    for day, value in pairs:
        stamp, number = pd.Timestamp(day), float(value)
        if stamp in values and values[stamp] != number:
            raise ValueError(f"Archive has conflicting values on {day}")
        values[stamp] = number
    archive = pd.Series(values, name="close").sort_index().to_frame()
    assert not archive.empty and archive.index.min() == pd.Timestamp("1967-01-05")
    archive["source"] = "011.idv.tw (close only)"
    for col in OHLC[:-1]:
        archive[col] = np.nan

    payload = json.loads((RAW / "yahoo_daily.json").read_text())
    if payload["chart"].get("error"):
        raise ValueError(payload["chart"]["error"])
    result = payload["chart"]["result"][0]
    days = (pd.to_datetime(result["timestamp"], unit="s", utc=True)
            .tz_convert("Asia/Taipei").normalize().tz_localize(None))
    yahoo = pd.DataFrame(result["indicators"]["quote"][0], index=days)[OHLC]
    yahoo = yahoo.round(2).dropna(subset=["close"])
    yahoo["source"] = "Yahoo Finance ^TWII"

    records = []
    for path in sorted(RAW.glob("twse_*.json")):
        payload = json.loads(path.read_text())
        if payload.get("stat") != "OK":
            raise ValueError(f"Invalid TWSE response: {path.name}")
        for row in payload["data"]:
            y, m, d = map(int, row[0].strip().split("/"))
            records.append({"date": pd.Timestamp(y + 1911, m, d),
                            **dict(zip(OHLC, [float(s.replace(",", "")) for s in row[1:5]])),
                            "source": "TWSE"})
    official = pd.DataFrame(records).set_index("date").sort_index()
    if not official.index.is_unique:
        raise ValueError("Duplicate official dates")

    # Preserve archived dates omitted by vendors (including makeup Saturdays).
    # Their OHLC stays null: never manufacture a candle from close-only data.
    # Before 1999 use archived closes; then Yahoo, with TWSE taking precedence.
    daily = pd.concat([archive, yahoo.loc["1999-01-01":], official])
    daily = daily.loc[~daily.index.duplicated(keep="last")].sort_index().loc[:as_of]
    assert daily.index.is_unique and daily.index.is_monotonic_increasing
    assert daily["close"].notna().all() and (daily["close"] > 0).all()
    candles = daily.dropna(subset=OHLC)
    assert (candles[OHLC] > 0).all().all()
    assert (candles["high"] >= candles[["open", "close"]].max(axis=1)).all()
    assert (candles["low"] <= candles[["open", "close"]].min(axis=1)).all()
    monthly_index = daily.index.to_period("M").unique()
    assert len(monthly_index) == len(pd.period_range(monthly_index.min(), monthly_index.max(), freq="M"))

    overlap = archive[["close"]].join(yahoo[["close"]], lsuffix="_archive", rsuffix="_yahoo", how="inner")
    overlap["difference"] = (overlap.close_archive - overlap.close_yahoo).round(2)
    differences = overlap.loc[overlap.difference.abs() > 1].copy()
    differences.index.name = "date"
    differences.to_csv(ROOT / "data" / "source_differences.csv", float_format="%.2f")
    archive_months = archive.close.resample("ME").last()
    final_months = daily.close.resample("ME").last()
    comparable = pd.concat([archive_months.rename("archive"), final_months.rename("selected")], axis=1).dropna()
    # Exclude the archive's unfinished final month when comparing month ends.
    comparable = comparable.loc[comparable.index.to_period("M") < archive.index.max().to_period("M")]
    month_diff = (comparable.archive - comparable.selected).round(2)
    audit = {
        "as_of": str(as_of.date()),
        "first_daily_date": str(daily.index.min().date()),
        "last_daily_date": str(daily.index.max().date()),
        "daily_rows": len(daily),
        "daily_rows_by_source": daily.source.value_counts().to_dict(),
        "first_ohlc_date": str(candles.index.min().date()),
        "close_only_dates_since_1999": [str(d.date()) for d in daily.loc[
            (daily.index >= "1999-01-01") & daily[OHLC].isna().any(axis=1)].index],
        "archive_numeric_records": len(pairs),
        "archive_unique_dates": len(archive),
        "archive_conflicting_duplicates": 0,
        "archive_yahoo_daily_overlap": len(overlap),
        "archive_yahoo_daily_differences_over_one_point": len(differences),
        "archive_selected_complete_months_compared": len(comparable),
        "archive_selected_month_end_max_difference": float(month_diff.abs().max()),
        "archive_selected_month_end_differences_over_one_point": {
            str(d.date()): float(v) for d, v in month_diff.items() if abs(v) > 1},
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(RAW.iterdir()) if p.is_file()},
    }
    daily.index.name = "date"
    daily[OHLC + ["source"]].to_csv(ROOT / "data" / "taiex_daily.csv", float_format="%.2f")
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
        out.append({
            "date": last, "period_start": period.start_time.date().isoformat(),
            "period_end": period.end_time.date().isoformat(),
            "first_trade_date": first.date().isoformat(),
            "last_trade_date": last.date().isoformat(),
            "open": group.open.iloc[0] if complete_ohlc else np.nan,
            "high": group.high.max() if complete_ohlc else np.nan,
            "low": group.low.min() if complete_ohlc else np.nan,
            "close": group.close.iloc[-1], "trading_days": len(group),
            "is_partial": bool(period.end_time.normalize() > min(as_of, end)),
            "has_ohlc": bool(complete_ohlc),
            "source": " + ".join(sorted(group.source.unique())),
        })
    if not out:
        raise ValueError("指定日期範圍沒有資料")
    frame = pd.DataFrame(out).set_index("date")
    assert frame.index.is_unique
    return frame


def configure_fonts() -> None:
    candidates = [os.environ.get("TAIEX_FONT", ""),
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
    fig.text(.075, .953, "TAIWAN  /  EQUITY HISTORY", fontsize=11, color=TEAL, weight="bold")
    fig.text(.075, .909, f"台股加權指數｜{label}線圖", fontsize=28, weight="bold")
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
        ax.grid(axis="y", color="#dce2da", linewidth=.65)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(axis="both", which="both", length=0, pad=9)
        ax.yaxis.tick_right()
        if chart == "close":
            ax.plot(frame.index, frame.close, color=TEAL, lw=1.5 if len(frame) < 1000 else .85)
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
            ax.xaxis.set_major_locator(mdates.YearLocator(5))
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
            events = [("1973", "1973 年月收盤高點", "max", (-30, 21)),
                      ("1990", "1990 年月收盤高點", "max", (-23, 24)),
                      ("2008", "2008 年月收盤低點", "min", (18, -35))]
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
    foot = "來源：011.idv.tw 歷史收盤彙整、TWSE、Yahoo Finance。官方資料優先；供應商缺日以收盤彙整補齊。"
    fig.text(.075, .083, foot, fontsize=9, color=MUTED)
    note = ("月線＝每月最後交易日；週線＝週一至週日彙整。價格指數，未含股息再投資。"
            if chart == "close" else "缺完整 OHLC 的期間以灰綠收盤點／線呈現（含 1999 年以前）；K 線紅漲綠跌。未含股息再投資。")
    fig.text(.075, .059, note, fontsize=9, color=MUTED)
    if frame.is_partial.iloc[-1]:
        fig.text(.075, .035, f"◆ 最後一筆{label}線尚未結束，截至 {latest:%Y-%m-%d}；早期資料未逐筆經官方驗證。", fontsize=9, color=ORANGE)
    else:
        fig.text(.075, .035, "早期資料未逐筆經官方驗證；資料来源與核對結果詳見 README / audit.json。", fontsize=9, color=MUTED)
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
        status = ["期間尚未結束" if p else "完整期間" for p in frame.is_partial]
        custom = np.column_stack([frame.source, frame.first_trade_date, frame.last_trade_date, status])
        fig.add_trace(go.Scatter(x=dates, y=frame.close.tolist(), name=f"{label}收盤價", mode="lines",
                                line={"color": TEAL, "width": 1.5}, customdata=custom,
                                hovertemplate="%{x}<br>收盤 %{y:,.2f}<br>%{customdata[3]}<br>%{customdata[0]}<extra></extra>",
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
                                    text=[f"{r.source}；{'尚未結束' if r.is_partial else '完整期間'}" for _, r in candles.iterrows()],
                                    visible=i * 3 == initial and chart == "candlestick"))
        for kind in ["close", "candlestick"]:
            visible = [False] * total_traces
            if kind == "close":
                visible[i * 3] = True
            else:
                visible[i * 3 + 1] = visible[i * 3 + 2] = True
            text = f"{label}線 · " + ("收盤折線" if kind == "close" else "K 線")
            buttons.append({"label": text, "method": "update", "args": [
                {"visible": visible}, {"title.text": f"台股加權指數｜{text}"}]})
    label = LABEL[interval]
    last = frames[interval].index.max().strftime("%Y-%m-%d")
    fig.update_layout(
        title={"text": f"台股加權指數｜{label}線 · " + ("收盤折線" if chart == "close" else "K 線"),
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
            {"buttons": buttons, "active": initial // 3 * 2 + (chart == "candlestick"), "x": .01, "y": 1.11, "xanchor": "left"},
            {"type": "buttons", "direction": "right", "x": .39, "y": 1.11, "xanchor": "left", "buttons": [
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
1967–1998 僅有收盤價；1999 起部分供應商缺日以歷史收盤資料補齊。缺完整開高低收的期間以灰綠點／線顯示，不產生 K 棒。<br>
早期與補缺資料未逐筆經官方驗證；完整缺日清單見 data/audit.json。<br>
來源：<a href="https://www.011.idv.tw/Taiex/FTaiexData.aspx">011.idv.tw</a>、
<a href="https://www.twse.com.tw/zh/indices/taiex/mi-5min-hist.html">臺灣證券交易所</a>、
<a href="https://finance.yahoo.com/quote/%5ETWII/history/">Yahoo Finance</a>。價格指數，未含股息再投資。
</div>'''
    html = html.replace("<head>", '<head><meta name="viewport" content="width=device-width, initial-scale=1"><title>台股加權指數歷史線圖</title>')
    html = html.replace("<body>", f'<body style="margin:0;background:{BG}">')
    html = html.replace("</body>", notes + "</body>")
    prefix.with_suffix(".html").write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", choices=list(LABEL), default="monthly", help="daily 日線 / weekly 週線 / monthly 月線")
    parser.add_argument("--chart", choices=["close", "candlestick"], default="close", help="收盤折線或 K 線")
    parser.add_argument("--start", type=date.fromisoformat, default=date(1967, 1, 1))
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
        frame.to_csv(ROOT / "data" / f"taiex_{interval}_bars.csv", float_format="%.2f")
    frame = frames[args.interval]
    prefix = args.output or ROOT / f"taiex_{args.interval}_{args.chart}"
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
