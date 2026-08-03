// 半年區間（上/下半年）選單的資料處理。
//
// 後端 ``/api/market/volume-heat`` 只吃「近 N 個交易日」，所以半年區間是在
// 前端切：選了半年就抓全歷史（跟「全部」同一個 query key，react-query 會共用
// 快取），再依日期篩出該半年。判讀值本來就是後端拿全歷史迴歸後算好的，切片
// 不會改變任何數字。

/** 上半年 = 1–6 月，下半年 = 7–12 月。 */
export interface HalfYear {
  year: number;
  half: 1 | 2;
}

// 冷熱資料從 2016 起算（對齊後端 market_volume_sync.BACKFILL_START）。
export const DATA_START_YEAR = 2016;

/** ``2025H2`` — 放進 ``<option value>`` 的字串。 */
export function halfYearValue(h: HalfYear): string {
  return `${h.year}H${h.half}`;
}

/** ``2025H2`` → ``{ year: 2025, half: 2 }``；格式不對回 null。 */
export function parseHalfYear(value: string): HalfYear | null {
  const m = /^(\d{4})H([12])$/.exec(value);
  if (!m) return null;
  return { year: Number(m[1]), half: Number(m[2]) as 1 | 2 };
}

/** ``2025 下``（選單與圖表標題共用的字）。 */
export function halfYearLabel(h: HalfYear): string {
  return `${h.year} ${h.half === 1 ? '上' : '下'}`;
}

/** 該半年的日期範圍（含頭含尾，ISO 字串）。 */
export function halfYearBounds(h: HalfYear): { start: string; end: string } {
  return h.half === 1
    ? { start: `${h.year}-01-01`, end: `${h.year}-06-30` }
    : { start: `${h.year}-07-01`, end: `${h.year}-12-31` };
}

/** ISO 日期 → 它落在哪個半年。 */
export function halfYearOf(date: string): HalfYear {
  const year = Number(date.slice(0, 4));
  return { year, half: Number(date.slice(5, 7)) <= 6 ? 1 : 2 };
}

/**
 * 選單選項：從 ``latestDate`` 所在的半年往回列到 ``startYear`` 上半年，新的在上。
 * ``latestDate`` 省略時用今天（資料還沒載入時的暫用值）。
 */
export function halfYearOptions(
  latestDate?: string,
  startYear: number = DATA_START_YEAR,
): HalfYear[] {
  const newest = latestDate ? halfYearOf(latestDate) : halfYearOf(todayIso());
  const out: HalfYear[] = [];
  for (let year = newest.year; year >= startYear; year--) {
    const halves: (1 | 2)[] = year === newest.year && newest.half === 1 ? [1] : [2, 1];
    for (const half of halves) out.push({ year, half });
  }
  return out;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/** 篩出落在該半年的列（輸入已是日期遞增，輸出維持順序）。 */
export function filterHalfYear<T extends { date: string }>(rows: T[], h: HalfYear): T[] {
  const { start, end } = halfYearBounds(h);
  return rows.filter((r) => r.date >= start && r.date <= end);
}
