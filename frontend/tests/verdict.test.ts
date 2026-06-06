import { describe, it, expect } from 'vitest';
import { side, isCall, pnl, verdict, fmtPct } from '../src/lib/verdict';
import type { Trade } from '../src/hooks/usePeople';

function trade(over: Partial<Trade>): Trade {
  return {
    raw_symbol: 'X', ticker: 'X', market: 'US', stock_name: null,
    direction: 'buy', price: null, quantity: null, trade_date: null, confidence: 0.9,
    pct_latest: null, pct_7d: null, pct_1m: null, base_price: null, price_status: null,
    ...over,
  };
}

describe('side mapping', () => {
  it('maps buy/bullish→long, sell/bearish→sell, hold→null', () => {
    expect(side('buy')).toBe('long');
    expect(side('bullish')).toBe('long');
    expect(side('sell')).toBe('sell');
    expect(side('bearish')).toBe('sell');
    expect(side('hold')).toBeNull();
  });
  it('isCall excludes hold', () => {
    expect(isCall(trade({ direction: 'hold' }))).toBe(false);
    expect(isCall(trade({ direction: 'buy' }))).toBe(true);
  });
});

describe('pnl', () => {
  it('long = +return, sell = −return', () => {
    expect(pnl(trade({ direction: 'buy', pct_latest: 0.1 }), 'pct_latest')).toBeCloseTo(0.1);
    expect(pnl(trade({ direction: 'sell', pct_latest: -0.08 }), 'pct_latest')).toBeCloseTo(0.08);
  });
  it('null when not evaluated or hold', () => {
    expect(pnl(trade({ direction: 'buy', pct_latest: null }), 'pct_latest')).toBeNull();
    expect(pnl(trade({ direction: 'hold', pct_latest: 0.1 }), 'pct_latest')).toBeNull();
  });
});

describe('verdict', () => {
  it('long winner → 跟單賺 / WIN', () => {
    const v = verdict(trade({ direction: 'buy', pct_latest: 0.05 }));
    expect(v).toMatchObject({ label: '跟單賺', cls: 'win', stamp: 'WIN' });
  });
  it('long loser → 住套房 / LOSS', () => {
    expect(verdict(trade({ direction: 'buy', pct_latest: -0.05 }))).toMatchObject({ label: '住套房', cls: 'lose' });
  });
  it('sell that dropped → 賣對了', () => {
    expect(verdict(trade({ direction: 'sell', pct_latest: -0.05 }))).toMatchObject({ label: '賣對了', cls: 'win' });
  });
  it('sell that rose → 賣早了', () => {
    expect(verdict(trade({ direction: 'sell', pct_latest: 0.05 }))).toMatchObject({ label: '賣早了', cls: 'lose' });
  });
  it('unevaluated → 追蹤中 / LIVE', () => {
    expect(verdict(trade({ pct_latest: null }))).toMatchObject({ label: '追蹤中', cls: 'wait', stamp: 'LIVE' });
  });
});

describe('fmtPct', () => {
  it('formats a fraction as a signed percent', () => {
    expect(fmtPct(0.13)).toBe('+13.0%');
    expect(fmtPct(-0.045)).toBe('-4.5%');
  });
});
