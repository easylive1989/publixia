// 大盤成交金額冷熱判讀 — level metadata shared by badge / meter / chart.
// Colors form a diverging scale (blue=cold pole, red=hot pole, neutral gray
// midpoint); identity never rides on color alone — the 判讀 label is always
// printed next to it (badge text, legend, tooltip).

export type HeatLevel = 'very_cold' | 'cold' | 'normal' | 'hot' | 'very_hot';

export const HEAT_LEVELS: HeatLevel[] = ['very_cold', 'cold', 'normal', 'hot', 'very_hot'];

export const HEAT_META: Record<HeatLevel, { zh: string; en: string; color: string; darkText: boolean }> = {
  very_cold: { zh: '明顯偏冷', en: 'VERY COLD', color: '#1a5fb0', darkText: false },
  cold:      { zh: '偏冷',     en: 'COLD',      color: '#7db3e0', darkText: true },
  normal:    { zh: '正常',     en: 'NORMAL',    color: '#d3cec5', darkText: true },
  hot:       { zh: '偏熱',     en: 'HOT',       color: '#e8975a', darkText: true },
  very_hot:  { zh: '明顯偏熱', en: 'VERY HOT',  color: '#a82a1c', darkText: false },
};

/** 億元 with thousands separators, no decimals (the sheet shows integers). */
export function fmtBillion(n: number): string {
  return Math.round(n).toLocaleString('en-US');
}

/**
 * ~`count` 個落在 [min, max] 內的整數刻度。
 *
 * 兩張圖共用：量能的量級隨市場差好幾個數量級（台股成交金額幾千億元、Nasdaq
 * 成交股數幾十億股），所以刻度不能寫死成「取到千位」——那在美股會全部歸零。
 */
export function niceTicks(min: number, max: number, count = 4): number[] {
  const raw = (max - min) / count;
  if (!(raw > 0)) return [];
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max; v += step) out.push(v);
  return out;
}

/** Percentile 0..1 → "PR 74" style integer string. */
export function fmtPercentile(p: number): string {
  return `PR ${Math.round(p * 100)}`;
}
