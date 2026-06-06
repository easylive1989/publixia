// Per-call scoring — the frontend mirror of backend/services/scoreboard.py.
// Keep the two in sync: side mapping + P&L sign + win threshold are identical.
import type { Direction, Trade } from '@/hooks/usePeople';

export type Side = 'long' | 'sell' | null;

export function side(direction: Direction): Side {
  if (direction === 'buy' || direction === 'bullish') return 'long';
  if (direction === 'sell' || direction === 'bearish') return 'sell';
  return null; // hold → not a tradeable call
}

export const isCall = (t: Trade): boolean => side(t.direction) !== null;

// Copy-trade P&L (fraction) for a given window: +return for long, −return for sell.
export function pnl(t: Trade, window: 'pct_7d' | 'pct_1m' | 'pct_latest'): number | null {
  const s = side(t.direction);
  const r = t[window];
  if (s === null || r == null) return null;
  return s === 'long' ? r : -r;
}

export interface Verdict {
  label: string;
  cls: 'win' | 'lose' | 'wait';
  stamp: string;
}

export function verdict(t: Trade): Verdict {
  const pl = pnl(t, 'pct_latest');
  if (pl == null) return { label: '追蹤中', cls: 'wait', stamp: 'LIVE' };
  if (side(t.direction) === 'sell') {
    return pl >= 0
      ? { label: '賣對了', cls: 'win', stamp: 'WIN' }
      : { label: '賣早了', cls: 'lose', stamp: 'MISS' };
  }
  return pl >= 0
    ? { label: '跟單賺', cls: 'win', stamp: 'WIN' }
    : { label: '住套房', cls: 'lose', stamp: 'LOSS' };
}

// fractions in (−0.045) → "−4.5%"
export const fmtPct = (v: number): string => (v > 0 ? '+' : '') + (v * 100).toFixed(1) + '%';
