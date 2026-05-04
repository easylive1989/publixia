import { describe, it, expect } from 'vitest';
import { alertTargetLabel, conditionLabel, thresholdPlaceholder } from '../src/lib/alert-labels';
import type { AlertRecord } from '../src/hooks/useAlerts';

const base: AlertRecord = {
  id: 1, target_type: 'indicator', target: 'taiex', indicator_key: null,
  condition: 'above', threshold: 0, window_n: null, enabled: 1,
  created_at: '2026-01-01T00:00:00Z', triggered_at: null, triggered_value: null,
};

describe('alertTargetLabel', () => {
  it('indicator key resolves to Chinese label', () => {
    expect(alertTargetLabel(base)).toBe('加權指數');
  });
  it('unknown indicator falls back to raw target', () => {
    expect(alertTargetLabel({ ...base, target: 'xxx' })).toBe('xxx');
  });
  it('stock_indicator joins ticker + indicator label', () => {
    expect(alertTargetLabel({
      ...base, target_type: 'stock_indicator', target: '2330.TW', indicator_key: 'per',
    })).toBe('2330.TW PER');
  });
  it('stock returns ticker as-is', () => {
    expect(alertTargetLabel({ ...base, target_type: 'stock', target: 'AAPL' })).toBe('AAPL');
  });
});

describe('conditionLabel', () => {
  it.each([
    ['above', '≥'],
    ['below', '≤'],
    ['percentile_above', '5y 百分位 ≥'],
    ['percentile_below', '5y 百分位 ≤'],
    ['yoy_above', 'YoY ≥'],
    ['yoy_below', 'YoY ≤'],
  ])('%s -> %s', (cond, expected) => {
    expect(conditionLabel({ ...base, condition: cond })).toBe(expected);
  });
  it('streak_above includes window_n', () => {
    expect(conditionLabel({ ...base, condition: 'streak_above', window_n: 7 })).toBe('連 7 日 ≥');
  });
});

describe('thresholdPlaceholder', () => {
  it('percentile family', () => {
    expect(thresholdPlaceholder('percentile_above')).toBe('百分位 0–100');
  });
  it('yoy family', () => {
    expect(thresholdPlaceholder('yoy_below')).toBe('YoY %（可正可負）');
  });
  it('default', () => {
    expect(thresholdPlaceholder('above')).toBe('門檻數值');
  });
});
