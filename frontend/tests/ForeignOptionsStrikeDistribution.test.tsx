import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ForeignOptionsStrikeDistribution } from '../src/components/foreign-futures/ForeignOptionsStrikeDistribution';
import type { ForeignFuturesResponse } from '../src/hooks/useForeignFutures';

function makeData(overrides?: Partial<ForeignFuturesResponse>): ForeignFuturesResponse {
  return {
    symbol: 'TX',
    name: 'TX 外資動向',
    currency: 'TWD',
    time_range: '1M',
    dates: ['2026-05-08', '2026-05-09'],
    candles: [
      { open: 17000, high: 17100, low: 16950, close: 17050, volume: 1 },
      { open: 17050, high: 17150, low: 17000, close: 17100, volume: 1 },
    ],
    cost: [null, null],
    net_position: [null, null],
    net_change: [null, null],
    unrealized_pnl: [null, null],
    realized_pnl: [0, 0],
    retail_ratio: [null, null],
    foreign_spot_net: [null, null],
    settlement_dates: [],
    options: {
      foreign_call_long_amount:  [null, null],
      foreign_call_short_amount: [null, null],
      foreign_put_long_amount:   [null, null],
      foreign_put_short_amount:  [null, null],
      detail_by_date: {},
      oi_by_strike: {
        date: '2026-05-09',
        expiry_months: ['202506', '202506W2', '202507'],
        near_month: '202506',
        by_expiry: {
          '202506': {
            strikes: [16500, 17000, 17500, 18000],
            call_oi: [0, 3500, 1800, 200],
            put_oi:  [400, 4200, 600, 0],
          },
          '202506W2': {
            strikes: [17000],
            call_oi: [50],
            put_oi:  [80],
          },
          '202507': {
            strikes: [17000, 17500],
            call_oi: [120, 60],
            put_oi:  [90, 30],
          },
        },
      },
    },
    ...overrides,
  };
}

describe('ForeignOptionsStrikeDistribution', () => {
  it('renders nothing when oi_by_strike block is missing', () => {
    const data = makeData();
    delete data.options!.oi_by_strike;
    const { container } = render(<ForeignOptionsStrikeDistribution data={data} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows market-wide caveat and the data date', () => {
    render(<ForeignOptionsStrikeDistribution data={makeData()} />);
    expect(screen.getByText(/各履約價未平倉量 \(OI\) 分布/)).toBeInTheDocument();
    expect(screen.getByText(/市場合計 · 2026-05-09/)).toBeInTheDocument();
    expect(screen.getByText(/TAIFEX 不公開身份別/)).toBeInTheDocument();
  });

  it('defaults to near-month and shows CALL/PUT totals for it', () => {
    render(<ForeignOptionsStrikeDistribution data={makeData()} />);
    // 202506 CALL totals = 3500+1800+200 = 5500
    // 202506 PUT  totals = 400+4200+600   = 5200
    expect(screen.getByText(/買權合計 5,500 口 · 賣權合計 5,200 口/)).toBeInTheDocument();
  });

  it('shows empty-state message when the selected expiry has no rows', () => {
    const data = makeData();
    data.options!.oi_by_strike = {
      date: '2026-05-09',
      expiry_months: [],
      near_month: null,
      by_expiry: {},
    };
    render(<ForeignOptionsStrikeDistribution data={data} />);
    expect(screen.getByText('此到期月份無 OI 資料。')).toBeInTheDocument();
  });
});
