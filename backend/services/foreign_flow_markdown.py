"""Render the 5-day 外資動向 snapshot as markdown.

1:1 Python port of the previous frontend implementation
(``frontend/src/lib/foreign-flow-markdown.ts``). Output is fed to the
Cloudflare Worker that calls Workers AI and also served raw by the
"download 5-day" UI button so the frontend and the AI pipeline share a
single source of truth.

Input is the payload produced by
``services.foreign_flow_payload.assemble_foreign_flow_payload`` — i.e.
exactly the JSON shape returned by ``GET /api/futures/tw/foreign-flow``.
"""
from __future__ import annotations

import math


TARGET_DAYS = 5
PROMPT_VERSION = "v1"

_IDENTITY_LABEL = {
    "foreign":          "外資",
    "investment_trust": "投信",
    "dealer":           "自營商",
}
_IDENTITY_ORDER = ("foreign", "investment_trust", "dealer")
_PUT_CALL_LABEL = {"CALL": "買權", "PUT": "賣權"}
_PUT_CALL_ORDER = ("CALL", "PUT")

_NA = "—"

PROMPT_TEMPLATE = (
    "> 你是個人交易者,擅長台指期短線技術分析。"
    "請根據以下最近交易日的外資期貨/選擇權/散戶多空比資料,產出:\n"
    "> 1. 外資多空動向解讀(口數變化、成本變化、損益狀態)\n"
    "> 2. TXO 選擇權三大法人布局解讀(買權/賣權、多/空)\n"
    "> 3. 散戶多空比觀察(常用作反向指標)\n"
    "> 4. 隔週(下週一~五)技術面交易計畫:看多/看空理由、進場區間、停損點、停利目標\n"
    "> 5. 主要風險訊號與觀察重點"
)


def _is_nan(v) -> bool:
    return isinstance(v, float) and math.isnan(v)


def _fmt_num(v, digits: int = 0) -> str:
    if v is None or _is_nan(v):
        return _NA
    if digits <= 0:
        # Match JS toLocaleString('en-US', { minimumFractionDigits: 0 }):
        # commas every 3, no decimal point.
        return f"{int(round(v)):,}"
    # Round half-up to ``digits`` and format with thousands separator.
    return f"{float(v):,.{digits}f}"


def _fmt_signed(v, digits: int = 0) -> str:
    if v is None or _is_nan(v):
        return _NA
    s = _fmt_num(abs(v), digits)
    if v > 0:
        return "+" + s
    if v < 0:
        return "-" + s
    return s


def _to_billions(v) -> str:
    """TAIFEX 千元 → 億元 (÷ 100,000), 2 decimals. Mirrors the TS helper."""
    if v is None or _is_nan(v):
        return _NA
    return f"{v / 100_000:.2f}"


def _slice_last_n(dates: list[str], n: int) -> tuple[list[int], list[str]]:
    total = len(dates)
    take = min(n, total)
    start = total - take
    indices = list(range(start, total))
    return indices, [dates[i] for i in indices]


def _date_label(date: str, settlement_set: set[str]) -> str:
    return f"{date} ✦" if date in settlement_set else date


def _build_kline_table(
    data: dict, indices: list[int], settlement_set: set[str],
) -> str:
    lines = [
        "## TX 期貨日線 (OHLCV)",
        "",
        "| 日期 | 開 | 高 | 低 | 收 | 量 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    candles = data["candles"]
    dates = data["dates"]
    for i in indices:
        c = candles[i] or {}
        lines.append(
            f"| {_date_label(dates[i], settlement_set)} "
            f"| {_fmt_num(c.get('open'))} "
            f"| {_fmt_num(c.get('high'))} "
            f"| {_fmt_num(c.get('low'))} "
            f"| {_fmt_num(c.get('close'))} "
            f"| {_fmt_num(c.get('volume'))} |"
        )
    lines.append("")
    lines.append("> ✦ 表示結算日")
    return "\n".join(lines)


def _build_foreign_futures_table(data: dict, indices: list[int]) -> str:
    lines = [
        "## 外資期貨多空未平倉 (大台等值口)",
        "",
        "| 日期 | 淨口數 | 日變動 | 持倉成本 (點) | 未實現損益 (NTD) | 已實現損益 (NTD) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    dates = data["dates"]
    for i in indices:
        lines.append(
            f"| {dates[i]} "
            f"| {_fmt_signed(data['net_position'][i])} "
            f"| {_fmt_signed(data['net_change'][i])} "
            f"| {_fmt_num(data['cost'][i], 0)} "
            f"| {_fmt_signed(data['unrealized_pnl'][i])} "
            f"| {_fmt_signed(data['realized_pnl'][i])} |"
        )
    lines.append("")
    lines.append("> 淨口數 = 多方未平倉 − 空方未平倉;持倉成本/未實現損益為近似值")
    return "\n".join(lines)


def _build_options_table(data: dict, indices: list[int]) -> str | None:
    opt = data.get("options")
    if not opt:
        return None

    lines = [
        "## TXO 選擇權三大法人未平倉 (口數 / 億元)",
        "",
        "| 日期 | 身份 | 買/賣 | 多方 OI | 空方 OI | 多方金額(億) | 空方金額(億) |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    detail_by_date = opt.get("detail_by_date", {})
    dates = data["dates"]
    printed = 0
    for i in indices:
        date = dates[i]
        rows = detail_by_date.get(date) or []
        if not rows:
            continue
        by_key = {(r["identity"], r["put_call"]): r for r in rows}
        for identity in _IDENTITY_ORDER:
            for put_call in _PUT_CALL_ORDER:
                r = by_key.get((identity, put_call))
                if not r:
                    continue
                lines.append(
                    f"| {date} "
                    f"| {_IDENTITY_LABEL[identity]} "
                    f"| {_PUT_CALL_LABEL[put_call]} "
                    f"| {_fmt_num(r['long_oi'])} "
                    f"| {_fmt_num(r['short_oi'])} "
                    f"| {_to_billions(r['long_amount'])} "
                    f"| {_to_billions(r['short_amount'])} |"
                )
                printed += 1

    if printed == 0:
        lines.append("| — | — | — | — | — | — | — |")
        lines.append("")
        lines.append("> 此期間無 TXO 三大法人資料")
    else:
        lines.append("")
        lines.append("> 金額單位為億元 (TAIFEX 千元 ÷ 100,000)")
    return "\n".join(lines)


def _build_spot_table(data: dict, indices: list[int]) -> str:
    lines = ["## 外資現貨淨買賣超 (TWSE 整體, 億元)", ""]
    spot = data["foreign_spot_net"]
    has_any = any(spot[i] is not None for i in indices)
    if not has_any:
        lines.append("> 此期間無外資現貨資料")
        return "\n".join(lines)
    lines.append("| 日期 | 外資現貨淨額 (億) |")
    lines.append("|---|---:|")
    dates = data["dates"]
    for i in indices:
        lines.append(f"| {dates[i]} | {_fmt_signed(spot[i], 2)} |")
    lines.append("")
    lines.append("> 正值=外資現貨買超;負值=外資現貨賣超")
    return "\n".join(lines)


def _format_expiry(expiry: str) -> str:
    # YYYYMM[Wn] → "YYYY/MM[ Wn]"
    if len(expiry) < 6 or not expiry[:6].isdigit():
        return expiry
    head = f"{expiry[:4]}/{expiry[4:6]}"
    tail = expiry[6:]
    return f"{head} {tail}" if tail else head


def _build_strike_oi_section(block: dict) -> str:
    lines = ["## 各履約價未平倉量 (OI) 分布 — 市場合計", ""]
    date = block.get("date")
    expiry_months: list[str] = block.get("expiry_months") or []
    by_expiry: dict = block.get("by_expiry") or {}

    if not date or not expiry_months:
        lines.append("> 尚無 TXO 各履約價未沖銷量資料")
        return "\n".join(lines)

    target_expiry = None
    near_month = block.get("near_month")
    if near_month and by_expiry.get(near_month):
        target_expiry = near_month
    else:
        for m in expiry_months:
            if by_expiry.get(m):
                target_expiry = m
                break

    lines.append(f"資料日: {date}")
    others = [_format_expiry(m) for m in expiry_months if m != target_expiry]
    if others:
        lines.append(f"其他可選到期月份: {', '.join(others)}")
    lines.append("")

    if not target_expiry:
        lines.append("> 此資料日無可用的履約價 OI 明細")
        return "\n".join(lines)

    s = by_expiry[target_expiry]
    strikes = s.get("strikes") or []
    call_oi = s.get("call_oi") or []
    put_oi  = s.get("put_oi")  or []
    n = len(strikes)

    # Trim leading/trailing zero rows so the table focuses on the live OI band.
    start = 0
    while start < n and (call_oi[start] or 0) == 0 and (put_oi[start] or 0) == 0:
        start += 1
    end = n - 1
    while end > start and (call_oi[end] or 0) == 0 and (put_oi[end] or 0) == 0:
        end -= 1

    lines.append(f"### 到期 {_format_expiry(target_expiry)}")
    lines.append("")

    if n == 0 or end < start:
        lines.append("> 此到期月份無 OI 資料")
        return "\n".join(lines)

    lines.append("| 履約價 | 買權 OI | 賣權 OI | 合計 |")
    lines.append("|---:|---:|---:|---:|")
    call_total = 0
    put_total  = 0
    for i in range(start, end + 1):
        strike = strikes[i]
        call = call_oi[i] or 0
        put  = put_oi[i]  or 0
        call_total += call
        put_total  += put
        strike_label = str(int(strike)) if float(strike).is_integer() else str(strike)
        lines.append(
            f"| {strike_label} | {_fmt_num(call)} | {_fmt_num(put)} | {_fmt_num(call + put)} |"
        )
    lines.append("")
    lines.append(
        f"> 單位:口;買權合計 {_fmt_num(call_total)},"
        f"賣權合計 {_fmt_num(put_total)};"
        f"TAIFEX 不公開身份別 (外資/投信/自營) 各履約價數據,"
        f"此為全市場合計"
    )
    return "\n".join(lines)


def _build_retail_table(data: dict, indices: list[int]) -> str:
    lines = ["## 散戶多空比 (%)", ""]
    ratio = data["retail_ratio"]
    has_any = any(ratio[i] is not None for i in indices)
    if not has_any:
        lines.append("> 此期間無散戶多空比資料")
        return "\n".join(lines)
    lines.append("| 日期 | 散戶多空比 (%) |")
    lines.append("|---|---:|")
    dates = data["dates"]
    for i in indices:
        v = ratio[i]
        cell = _NA if v is None or _is_nan(v) else _fmt_signed(v, 2)
        lines.append(f"| {dates[i]} | {cell} |")
    lines.append("")
    lines.append("> 由 TAIFEX 大額交易人資料推算 (全市場 OI − 大戶 OI);常作為反向指標參考")
    return "\n".join(lines)


def build_foreign_flow_markdown(payload: dict, generated_date: str) -> str:
    """Render the markdown snapshot for the trailing 5 trading days.

    Args:
        payload: shape returned by
            ``assemble_foreign_flow_payload`` / the foreign-flow API.
        generated_date: ``YYYY-MM-DD`` string printed in the header. The
            caller decides what "today" means (route uses Asia/Taipei).
    """
    dates = payload["dates"]
    indices, sliced_dates = _slice_last_n(dates, TARGET_DAYS)
    settlement_set = set(payload.get("settlement_dates") or [])

    start_date = sliced_dates[0]  if sliced_dates else ""
    end_date   = sliced_dates[-1] if sliced_dates else ""

    header = "\n".join([
        f"# 台指期 · 外資動向 {len(indices)} 日快照",
        f"資料期間: {start_date} ~ {end_date} ({len(indices)} 個交易日)",
        f"產出時間: {generated_date}",
        "",
        "## AI 分析請求 (可直接複製給 ChatGPT/Claude)",
        "",
        PROMPT_TEMPLATE,
        "",
        "---",
        "",
    ])

    sections: list[str] = [
        _build_kline_table(payload, indices, settlement_set),
        _build_spot_table(payload, indices),
        _build_foreign_futures_table(payload, indices),
    ]
    options_table = _build_options_table(payload, indices)
    if options_table:
        sections.append(options_table)
    strike_block = (payload.get("options") or {}).get("oi_by_strike")
    if strike_block:
        sections.append(_build_strike_oi_section(strike_block))
    sections.append(_build_retail_table(payload, indices))

    return header + "\n\n".join(sections) + "\n"


def build_filename(generated_date: str) -> str:
    return f"foreign-flow_{generated_date}.md"
