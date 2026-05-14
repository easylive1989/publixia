"""Tests for services.foreign_flow_markdown.

These mirror the invariants of the previous TS implementation
(``frontend/src/lib/foreign-flow-markdown.ts``):

* same 5-day window, header format and prompt template,
* same section ordering and column headers,
* same number formatting rules (千 位分隔、億元 換算、有號數).
"""
from services.foreign_flow_markdown import (
    PROMPT_TEMPLATE,
    PROMPT_VERSION,
    TARGET_DAYS,
    build_filename,
    build_foreign_flow_markdown,
)


def _candle(o, h, l, c, v):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def _make_payload(**overrides) -> dict:
    """Construct a 5-day payload with sensible defaults for testing."""
    dates = ["2026-05-08", "2026-05-09", "2026-05-12", "2026-05-13", "2026-05-14"]
    base = {
        "symbol":   "TX",
        "name":     "台指期",
        "currency": "TWD",
        "time_range": "1M",
        "dates": dates,
        "candles": [
            _candle(17000, 17100, 16900, 17050, 120_000),
            _candle(17050, 17200, 17000, 17150, 130_000),
            _candle(17150, 17300, 17100, 17280, 140_000),
            _candle(17280, 17350, 17200, 17220, 110_000),
            _candle(17220, 17400, 17150, 17380, 150_000),
        ],
        "cost":          [16000.0, 16100.0, 16200.0, 16300.0, 16400.0],
        "net_position":  [10_000, 11_000, -2_000, 9_500, 12_000],
        "net_change":    [None, 1_000, -13_000, 11_500, 2_500],
        "unrealized_pnl":[2_100_000.0, 2_310_000.0, -432_000.0, 1_843_000.0, 4_704_000.0],
        "realized_pnl":  [0.0, 0.0, -1_500_000.0, 0.0, 500_000.0],
        "retail_ratio":  [-5.25, -3.10, 4.55, -1.20, 2.80],
        "foreign_spot_net": [12.34, -5.67, None, 8.90, 0.00],
        "settlement_dates": ["2026-05-14"],
        "options": {
            "foreign_call_long_amount":  [None, None, None, None, 2_400_000.0],
            "foreign_call_short_amount": [None, None, None, None, 2_200_000.0],
            "foreign_put_long_amount":   [None, None, None, None,   180_000.0],
            "foreign_put_short_amount":  [None, None, None, None,   160_000.0],
            "detail_by_date": {
                "2026-05-14": [
                    {"identity": "foreign",          "put_call": "CALL",
                     "long_oi": 13_000, "short_oi": 12_000,
                     "long_amount": 2_400_000.0, "short_amount": 2_200_000.0},
                    {"identity": "foreign",          "put_call": "PUT",
                     "long_oi": 18_000, "short_oi": 15_000,
                     "long_amount":   180_000.0, "short_amount":   160_000.0},
                    {"identity": "investment_trust", "put_call": "CALL",
                     "long_oi": 100, "short_oi": 50,
                     "long_amount":     1_000.0, "short_amount":      500.0},
                    {"identity": "investment_trust", "put_call": "PUT",
                     "long_oi": 200, "short_oi": 80,
                     "long_amount":     2_000.0, "short_amount":      800.0},
                    {"identity": "dealer",           "put_call": "CALL",
                     "long_oi": 300, "short_oi": 250,
                     "long_amount":     3_000.0, "short_amount":    2_500.0},
                    {"identity": "dealer",           "put_call": "PUT",
                     "long_oi": 400, "short_oi": 380,
                     "long_amount":     4_000.0, "short_amount":    3_800.0},
                ],
            },
            "oi_by_strike": {
                "date": "2026-05-14",
                "expiry_months": ["202505", "202505W2", "202506"],
                "near_month": "202505",
                "by_expiry": {
                    "202505": {
                        "strikes":  [16800.0, 17000.0, 17200.0, 17400.0, 17600.0],
                        "call_oi":  [0, 5_000, 8_000, 3_000, 0],
                        "put_oi":   [0, 4_000, 6_000, 2_000, 0],
                    },
                    "202505W2": {"strikes": [], "call_oi": [], "put_oi": []},
                    "202506":   {"strikes": [], "call_oi": [], "put_oi": []},
                },
            },
        },
    }
    base.update(overrides)
    return base


def _md(payload=None, generated="2026-05-14"):
    return build_foreign_flow_markdown(payload or _make_payload(), generated)


# ── header / prompt ────────────────────────────────────────────────────


def test_header_contains_date_range_and_count():
    md = _md()
    assert md.startswith("# 台指期 · 外資動向 5 日快照\n")
    assert "資料期間: 2026-05-08 ~ 2026-05-14 (5 個交易日)" in md
    assert "產出時間: 2026-05-14" in md


def test_prompt_template_embedded():
    md = _md()
    assert PROMPT_TEMPLATE in md
    assert "## AI 分析請求 (可直接複製給 ChatGPT/Claude)" in md
    # All 5 bullets present.
    for n in (1, 2, 3, 4, 5):
        assert f"> {n}." in md


def test_target_days_is_five():
    assert TARGET_DAYS == 5


def test_prompt_version_constant_exists_for_repo_writes():
    assert PROMPT_VERSION == "v1"


# ── K-line table ───────────────────────────────────────────────────────


def test_kline_table_uses_settlement_marker_on_settlement_day():
    md = _md()
    # 2026-05-14 is in settlement_dates → ✦ appended
    assert "| 2026-05-14 ✦ |" in md
    # Other days don't get the marker
    assert "| 2026-05-08 |" in md
    assert "| 2026-05-08 ✦" not in md
    assert "> ✦ 表示結算日" in md


def test_kline_numbers_have_thousand_separators():
    md = _md()
    # volume 120_000 → 120,000
    assert "| 120,000 |" in md
    assert "| 150,000 |" in md


# ── foreign spot table ─────────────────────────────────────────────────


def test_spot_table_renders_signed_values():
    md = _md()
    assert "## 外資現貨淨買賣超 (TWSE 整體, 億元)" in md
    assert "| 2026-05-08 | +12.34 |" in md
    assert "| 2026-05-09 | -5.67 |" in md
    # Day with no data falls back to the NA marker
    assert "| 2026-05-12 | — |" in md
    # Zero → unsigned formatted
    assert "| 2026-05-14 | 0.00 |" in md


def test_spot_table_falls_back_when_all_null():
    payload = _make_payload(foreign_spot_net=[None] * 5)
    md = _md(payload)
    assert "此期間無外資現貨資料" in md
    # And the table proper isn't rendered.
    assert "| 日期 | 外資現貨淨額 (億) |" not in md


# ── foreign futures table ──────────────────────────────────────────────


def test_foreign_futures_table_signed_columns():
    md = _md()
    # Day 1 has net_change=None → renders as NA
    assert "| 2026-05-08 | +10,000 | — | 16,000 | +2,100,000 | 0 |" in md
    # Day 3 has negative net_position and large negative net_change
    assert "| 2026-05-12 | -2,000 | -13,000 | 16,200 | -432,000 | -1,500,000 |" in md


# ── options table ──────────────────────────────────────────────────────


def test_options_table_emits_all_six_rows_for_a_date():
    md = _md()
    assert "## TXO 選擇權三大法人未平倉 (口數 / 億元)" in md
    # 3 identities × 2 put/call = 6 rows for 2026-05-14
    assert "| 2026-05-14 | 外資 | 買權 | 13,000 | 12,000 | 24.00 | 22.00 |" in md
    assert "| 2026-05-14 | 外資 | 賣權 | 18,000 | 15,000 | 1.80 | 1.60 |" in md
    assert "| 2026-05-14 | 投信 | 買權 | 100 | 50 | 0.01 | 0.01 |" in md
    assert "| 2026-05-14 | 自營商 | 賣權 | 400 | 380 | 0.04 | 0.04 |" in md


def test_options_section_skipped_when_payload_lacks_block():
    payload = _make_payload()
    payload["options"] = None  # type: ignore[assignment]
    md = _md(payload)
    assert "## TXO 選擇權三大法人未平倉" not in md
    assert "## 各履約價未平倉量" not in md


def test_options_table_empty_branch_when_no_rows_in_window():
    payload = _make_payload()
    payload["options"]["detail_by_date"] = {}
    md = _md(payload)
    assert "此期間無 TXO 三大法人資料" in md


# ── strike OI section ──────────────────────────────────────────────────


def test_strike_oi_uses_near_month_and_trims_zero_padding():
    md = _md()
    assert "## 各履約價未平倉量 (OI) 分布 — 市場合計" in md
    assert "資料日: 2026-05-14" in md
    assert "### 到期 2025/05" in md
    # Leading/trailing zero rows trimmed → 17000/17200/17400 retained,
    # 16800 and 17600 dropped.
    assert "| 17000 | 5,000 | 4,000 | 9,000 |" in md
    assert "| 17200 | 8,000 | 6,000 | 14,000 |" in md
    assert "| 17400 | 3,000 | 2,000 | 5,000 |" in md
    assert "| 16800 |" not in md
    assert "| 17600 |" not in md
    # Totals + footnote with formatted expiry names.
    assert "買權合計 16,000" in md
    assert "賣權合計 12,000" in md
    # "其他可選到期月份" lists the other expiries with formatted names.
    assert "2025/05 W2" in md
    assert "2025/06" in md


def test_strike_oi_section_skipped_when_block_absent():
    payload = _make_payload()
    payload["options"]["oi_by_strike"] = None  # type: ignore[assignment]
    md = _md(payload)
    assert "## 各履約價未平倉量" not in md


# ── retail table ───────────────────────────────────────────────────────


def test_retail_table_renders_two_decimal_signed():
    md = _md()
    assert "## 散戶多空比 (%)" in md
    assert "| 2026-05-08 | -5.25 |" in md
    assert "| 2026-05-14 | +2.80 |" in md


def test_retail_table_fallback_when_all_null():
    payload = _make_payload(retail_ratio=[None] * 5)
    md = _md(payload)
    assert "此期間無散戶多空比資料" in md


# ── windowing ──────────────────────────────────────────────────────────


def test_handles_fewer_than_five_days():
    payload = _make_payload(
        dates=["2026-05-13", "2026-05-14"],
        candles=[_candle(1, 2, 1, 2, 3), _candle(2, 3, 2, 3, 4)],
        cost=[1.0, 2.0],
        net_position=[1, 2],
        net_change=[None, 1],
        unrealized_pnl=[0.0, 0.0],
        realized_pnl=[0.0, 0.0],
        retail_ratio=[0.5, 1.5],
        foreign_spot_net=[1.0, 2.0],
    )
    payload["options"]["detail_by_date"] = {}
    md = _md(payload)
    assert "# 台指期 · 外資動向 2 日快照\n" in md
    assert "資料期間: 2026-05-13 ~ 2026-05-14 (2 個交易日)" in md


def test_build_filename_format():
    assert build_filename("2026-05-14") == "foreign-flow_2026-05-14.md"
