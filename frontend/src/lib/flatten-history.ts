export interface ChartRow {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ma5: number | null;
  ma20: number | null;
  ma60: number | null;
  rsi14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  change_pct: number | null;
}

export interface OhlcvSeries {
  ticker: string;
  dates: string[];
  candles: {
    open:   number;
    high:   number;
    low:    number;
    close:  number;
    volume: number;
  }[];
  indicators: {
    ma5:            (number | null)[];
    ma20:           (number | null)[];
    ma60:           (number | null)[];
    rsi14:          (number | null)[];
    macd:           (number | null)[];
    macd_signal:    (number | null)[];
    macd_histogram: (number | null)[];
  };
}

export function flattenHistory(data: OhlcvSeries): ChartRow[] {
  const { dates, candles, indicators } = data;
  const out: ChartRow[] = [];
  for (let i = 0; i < dates.length; i++) {
    const c = candles[i];
    const prev = i > 0 ? candles[i - 1].close : null;
    const change_pct =
      prev != null && prev !== 0 ? ((c.close - prev) / prev) * 100 : null;
    out.push({
      date: dates[i],
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume,
      ma5: indicators.ma5[i] ?? null,
      ma20: indicators.ma20[i] ?? null,
      ma60: indicators.ma60[i] ?? null,
      rsi14: indicators.rsi14[i] ?? null,
      macd: indicators.macd[i] ?? null,
      macd_signal: indicators.macd_signal[i] ?? null,
      macd_histogram: indicators.macd_histogram[i] ?? null,
      change_pct,
    });
  }
  return out;
}
