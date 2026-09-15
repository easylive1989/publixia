import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { SentimentTable } from '../src/components/SentimentTable';
import type { MarketHeatDay } from '../src/hooks/useMarketHeat';
import { MARKETS } from '../src/lib/markets';

const TW = MARKETS[0];

function day(date: string, index: number, score?: number): MarketHeatDay {
  return {
    date,
    index_close: index,
    turnover: 6_000,
    expected_turnover: 10_000,
    volume_ratio: .6,
    residual: -.51,
    percentile: .1,
    level: 'very_cold',
    label: '明顯偏冷',
    sentiment: score === undefined ? null : {
      score,
      label: score < 40 ? '恐懼' : '中性',
      method: 'tw_fear_greed_proxy_v1',
      components: {
        momentum: 20, drawdown: 40, volatility: 50, breadth: 25, deviation: 30,
      },
    },
  };
}

describe('<SentimentTable />', () => {
  it('puts the calculated sentiment and market index in the same newest-first table', () => {
    render(<SentimentTable rows={[
      day('2026-09-14', 45862.52, 38.55),
      day('2026-09-15', 45511.49, 33.91),
    ]} market={TW} />);

    const table = screen.getByRole('table');
    for (const header of ['日期', '自算情緒指數', '市場情緒', '加權指數']) {
      expect(within(table).getByText(header)).toBeInTheDocument();
    }
    const rows = within(table).getAllByRole('row');
    expect(rows[1]).toHaveTextContent('2026-09-15');
    expect(rows[1]).toHaveTextContent('33.91');
    expect(rows[1]).toHaveTextContent('恐懼');
    expect(rows[1]).toHaveTextContent('45,511.49');
  });

  it('shows an explicit backfill state when breadth is missing', () => {
    render(<SentimentTable rows={[day('2026-09-15', 45511.49)]} market={TW} />);
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByText('等待漲跌家數')).toBeInTheDocument();
  });
});
