# 抽取排除「資產配置／題材」抽象詞 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 AI 抽取不再把「動能／題材／核心部位」等資產配置抽象詞當成個股交易，並升版觸發歷史貼文重抽以清掉既有錯誤。

**Architecture:** 純 prompt 工程：在 `_SYSTEM_PROMPT` 加一條類別排除規則 + 一個 few-shot 反例，並把 `PROMPT_VERSION` v4→v5。LLM 行為無法確定性測試，以「prompt 含預期內容 + 版本已升」的 regression test 鎖住意圖；既有 mock 測試維持綠。

**Tech Stack:** Python、pytest（mock `run_ai`）。

**測試指令：** 從 repo 根 `python3 -m pytest tests/test_trade_extraction.py -v`。

**前置：** 在 `feat/prompt-exclude-allocation` 分支。spec 在 `docs/superpowers/specs/2026-06-05-extraction-exclude-allocation-terms-design.md`。

---

## File Structure

- **Modify** `backend/services/trade_extraction.py` — `_SYSTEM_PROMPT`（加規則 + 反例）、`PROMPT_VERSION`（v4→v5）。
- **Modify** `tests/test_trade_extraction.py` — 新增 regression 測試鎖住 prompt 內容與版本。

---

## Task 1: regression 測試鎖住 prompt 意圖 + 版本

**Files:**
- Modify: `tests/test_trade_extraction.py`
- (實作對象) `backend/services/trade_extraction.py`

- [ ] **Step 1: Write the failing test**

在 `tests/test_trade_extraction.py` 末尾追加：

```python
def test_prompt_version_bumped_to_v5():
    assert te.PROMPT_VERSION == "v5"


def test_prompt_excludes_allocation_abstractions():
    # 類別排除規則 + few-shot 反例的關鍵字必須在 system prompt 裡，
    # 避免日後不小心被刪（LLM 行為本身無法確定性 unit-test）。
    prompt = te._SYSTEM_PROMPT
    assert "題材分類" in prompt          # 排除規則
    assert "核心部位" in prompt          # 排除規則列舉
    assert "下半年趨勢題材" in prompt    # few-shot 反例原文
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_trade_extraction.py::test_prompt_version_bumped_to_v5 tests/test_trade_extraction.py::test_prompt_excludes_allocation_abstractions -v`
Expected: FAIL — `PROMPT_VERSION` 仍是 `"v4"`；prompt 尚無「題材分類／下半年趨勢題材」等字串。

- [ ] **Step 3: Write minimal implementation**

在 `backend/services/trade_extraction.py`：

(a) 升版：

```python
PROMPT_VERSION = "v5"
```

(b) 在 `_SYSTEM_PROMPT` 的【抓取範圍】區塊，於這一行之後：

```
- 一律忽略：個別產業／板塊的籠統說法、原物料、匯率、純情緒抒發、與投資無關的生活內容。美股大盤（道瓊、那斯達克、S&P）目前先略過。
```

新增一行排除規則：

```
- 一律忽略「投資組合配置／選股策略／題材分類」這類抽象說法——動能、價值股、成長股、趨勢題材、某某題材、核心部位、衛星部位、現金部位、存股部位等，都不是具名個股。即使句中對它們有買賣動作（砍掉動能部位、布局趨勢題材、核心部位續抱），也不可當成交易；raw_symbol 必須能對應到某一檔具體個股／ETF。
```

(c) 在【範例】區塊，於「拒買國巨」反例之後、結尾「只輸出符合 schema 的 JSON」之前，新增 few-shot 反例：

```
貼文：「我的做法是把前陣子追動能的部位砍掉，剛好有現金可以逢低布局下半年趨勢題材，核心部位就是Hold&Hold。」
輸出：{"trades":[]}
（動能／下半年趨勢題材／核心部位是配置與題材分類的抽象說法，不是具名個股，即使有砍掉／布局／Hold 動作也不抓）
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_trade_extraction.py -v`
Expected: 全部 PASS（既有 5 個 mock 測試 + 新增 2 個 regression）。

- [ ] **Step 5: Commit**

```bash
git add backend/services/trade_extraction.py tests/test_trade_extraction.py
git commit -m "feat(extraction): prompt v5 排除資產配置/題材抽象詞 + 重抽"
```

---

## 驗收

- [ ] `python3 -m pytest tests/test_trade_extraction.py -v` 全綠（7 個）。
- [ ] 部署後實測：圖上那則「動能/趨勢題材/核心部位」貼文經重抽後回 `{"trades":[]}`，三個錯誤 chip 消失（每 30 分鐘一批，歷史貼文逐步重抽到 v5）。
