"""POSIX crontab 字串 → APScheduler ``CronTrigger``。

**為什麼不用 ``CronTrigger.from_crontab``。** 它收的字串長得跟 crontab 一模一
樣，卻把星期欄位原封不動餵給 APScheduler 自己的 ``day_of_week`` 欄位 —— 而那
個欄位是 **0=週一**，POSIX crontab 是 **0=週日**。於是 ``0 13 * * 1-5`` 這種
「週一到週五」的寫法，實際掛上去變成**週二到週六**：整份排程往後平移一天，
週一完全不跑、週六多跑一次。

這個錯不會有任何聲音。cron 解析得過（所以開機不會通報）、job 掛得上、被平移
到的那幾天也都正常執行，只有「週一沒有盤中判讀」這個症狀 —— 而 Discord 上
「什麼都沒有」跟「job 沒排到」長得一模一樣，正是 CLAUDE.md 那條「沒有靜默失
敗」要擋掉的東西。2026-08-10（週一）沒有大盤判讀就是它。

所以星期欄位在這裡先展開成明確的英文星期名（``mon,tue,…``）再交給
APScheduler：名稱沒有 0 到底是週日還是週一的歧義，``scheduler_jobs`` 表裡既
有的列不必改寫，手動編輯那張表的人也可以照 README 寫 POSIX 語意。
"""
from apscheduler.triggers.cron import CronTrigger

# APScheduler 的 day_of_week 順序（0=mon）。輸出照這個順序排，純粹為了可讀。
_APS_ORDER = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# POSIX crontab 的星期編號：0=週日、1=週一 … 6=週六（7 也是週日）。
_POSIX_INDEX = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}

_FIELDS = ("minute", "hour", "day", "month", "day_of_week")


def _posix_dow(token: str, field: str) -> int:
    """單一星期 token（數字或英文縮寫）→ POSIX 星期編號 0–6。"""
    text = token.strip().lower()
    if text in _POSIX_INDEX:
        return _POSIX_INDEX[text]
    try:
        value = int(text)
    except ValueError:
        raise ValueError(
            f"星期欄位看不懂的值 {token!r}（欄位 {field!r}）—— "
            f"只收 0-7 或 {'/'.join(_POSIX_INDEX)}"
        ) from None
    if not 0 <= value <= 7:
        raise ValueError(f"星期欄位 {token!r} 超出 0-7（欄位 {field!r}）")
    return 0 if value == 7 else value  # POSIX 的 7 跟 0 都是週日


def translate_day_of_week(field: str) -> str:
    """POSIX 星期欄位 → APScheduler 吃的英文星期清單。

    支援 crontab 的全部寫法：``*``、單值、清單 ``1,3``、區間 ``1-5``、步進
    ``*/2`` 與 ``1-5/2``，以及跨週末的區間 ``5-1``（週五到週一）。
    """
    text = field.strip()
    if text == "*":
        return "*"

    days: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"星期欄位 {field!r} 有空的區段")

        base, _, step_text = part.partition("/")
        step = 1
        if step_text:
            try:
                step = int(step_text)
            except ValueError:
                raise ValueError(
                    f"星期欄位 {part!r} 的步進值 {step_text!r} 不是數字"
                ) from None
            if step < 1:
                raise ValueError(f"星期欄位 {part!r} 的步進值必須 ≥ 1")

        base = base.strip()
        if base == "*":
            first, last = 0, 6
        elif "-" in base:
            low, _, high = base.partition("-")
            first, last = _posix_dow(low, field), _posix_dow(high, field)
        else:
            first = _posix_dow(base, field)
            # 裸的 `5/2` 在 crontab 裡是「從週五起每 2 天」，`5` 則只有週五。
            last = 6 if step_text else first

        # 對 7 取模 → `5-1`（週五~週一）這種跨週末的區間也能展開。
        span = ((last - first) % 7) + 1
        days.update((first + offset) % 7 for offset in range(0, span, step))

    return ",".join(name for name in _APS_ORDER if _POSIX_INDEX[name] in days)


def crontab_trigger(expr: str, timezone) -> CronTrigger:
    """5 欄位 POSIX cron 字串 → ``CronTrigger``（星期照 POSIX 語意解讀）。"""
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(
            f"cron 需要 5 個欄位（分 時 日 月 星期），{expr!r} 有 {len(fields)} 個"
        )
    values = dict(zip(_FIELDS, fields))
    values["day_of_week"] = translate_day_of_week(values["day_of_week"])
    return CronTrigger(**values, timezone=timezone)
