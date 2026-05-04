import { describe, it, expect } from 'vitest';
import { flattenHistory } from '../src/lib/flatten-history';

const sample = {
  ticker: 'X',
  name: 'X',
  currency: 'TWD',
  time_range: '3M',
  dates: ['2026-04-30', '2026-05-01', '2026-05-02'],
  candles: [
    { open: 100, high: 105, low: 98, close: 102, volume: 1000 },
    { open: 102, high: 108, low: 101, close: 107, volume: 1200 },
    { open: 107, high: 109, low: 100, close: 101, volume: 900 },
  ],
  indicators: {
    ma5: [null, null, 103],
    ma20: [null, null, null],
    ma60: [null, null, null],
    rsi14: [null, null, 55],
    macd: [null, 1, 2],
    macd_signal: [null, 0, 1],
    macd_histogram: [null, 1, 1],
  },
};

describe('flattenHistory', () => {
  it('zips arrays to rows of equal length', () => {
    const rows = flattenHistory(sample);
    expect(rows).toHaveLength(3);
    expect(rows[0].date).toBe('2026-04-30');
    expect(rows[2].close).toBe(101);
    expect(rows[2].ma5).toBe(103);
  });

  it('first row change_pct is null; later rows compute (close - prev_close) / prev * 100', () => {
    const rows = flattenHistory(sample);
    expect(rows[0].change_pct).toBeNull();
    expect(rows[1].change_pct).toBeCloseTo(4.9019, 3);
    expect(rows[2].change_pct).toBeCloseTo(-5.6074, 3);
  });
});
