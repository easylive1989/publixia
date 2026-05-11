import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ForeignOptionsDetailTable } from '../src/components/foreign-futures/ForeignOptionsDetailTable';
import type { ForeignFuturesResponse } from '../src/hooks/useForeignFutures';

function makeData(): ForeignFuturesResponse {
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
      foreign_call_long_amount:  [null, 2_488_000],
      foreign_call_short_amount: [null, 2_345_000],
      foreign_put_long_amount:   [null,   247_000],
      foreign_put_short_amount:  [null,   166_000],
      detail_by_date: {
        '2026-05-09': [
          { identity: 'foreign', put_call: 'CALL',
            long_oi: 12862, short_oi: 11092,
            long_amount: 2_488_000, short_amount: 2_345_000 },
          { identity: 'foreign', put_call: 'PUT',
            long_oi: 18494, short_oi: 14943,
            long_amount: 247_000, short_amount: 166_000 },
          { identity: 'investment_trust', put_call: 'CALL',
            long_oi: 1, short_oi: 430,
            long_amount: 0, short_amount: 150_000 },
          { identity: 'investment_trust', put_call: 'PUT',
            long_oi: 127, short_oi: 0,
            long_amount: 0, short_amount: 0 },
          { identity: 'dealer', put_call: 'CALL',
            long_oi: 18680, short_oi: 16884,
            long_amount: 2_940_000, short_amount: 3_104_000 },
          { identity: 'dealer', put_call: 'PUT',
            long_oi: 34609, short_oi: 29268,
            long_amount: 278_000, short_amount: 349_000 },
        ],
      },
    },
  };
}

describe('ForeignOptionsDetailTable', () => {
  it('renders nothing when options block is missing', () => {
    const data = makeData();
    delete data.options;
    const { container } = render(<ForeignOptionsDetailTable data={data} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows CALL and PUT sub-tables with all 3 identities for the latest date', () => {
    render(<ForeignOptionsDetailTable data={makeData()} />);

    // Card title + sub-table headings
    expect(screen.getByText(/TXO 三大法人 每日明細/)).toBeInTheDocument();
    expect(screen.getByText(/買權 \(CALL\)/)).toBeInTheDocument();
    expect(screen.getByText(/賣權 \(PUT\)/)).toBeInTheDocument();

    // 3 identities in each sub-table = 6 row labels total
    expect(screen.getAllByText('外資')).toHaveLength(2);
    expect(screen.getAllByText('投信')).toHaveLength(2);
    expect(screen.getAllByText('自營商')).toHaveLength(2);
  });

  it('renders amounts in 億元 with 2 decimals (long_amount 2,488,000 千 → 24.88 億)', () => {
    render(<ForeignOptionsDetailTable data={makeData()} />);
    // Foreign CALL long: 2,488,000 千元 ÷ 100,000 = 24.88
    expect(screen.getByText('24.88')).toBeInTheDocument();
    // Foreign CALL short: 2,345,000 千元 ÷ 100,000 = 23.45
    expect(screen.getByText('23.45')).toBeInTheDocument();
  });

  it('renders OI lots with thousand separators', () => {
    render(<ForeignOptionsDetailTable data={makeData()} />);
    expect(screen.getByText('12,862')).toBeInTheDocument();   // foreign CALL long_oi
    expect(screen.getByText('29,268')).toBeInTheDocument();   // dealer PUT short_oi
  });

  it('shows empty-state message when selected date has no rows', () => {
    const data = makeData();
    data.options!.detail_by_date = {};
    render(<ForeignOptionsDetailTable data={data} />);
    expect(screen.getByText('此日無 TXO 三大法人資料。')).toBeInTheDocument();
  });
});
