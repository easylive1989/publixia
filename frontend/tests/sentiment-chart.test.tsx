import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SentimentChart } from '../src/components/SentimentChart';
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

describe('<SentimentChart />', () => {
  it('draws sentiment and the market index as two lines instead of a table', async () => {
    const { container } = render(<SentimentChart rows={[
      day('2026-09-14', 45862.52, 38.55),
      day('2026-09-15', 45511.49, 33.91),
    ]} market={TW} />);

    expect(screen.getByRole('heading', { name: '自算恐懼貪婪指數 vs 加權指數' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: '自算恐懼貪婪指數與加權指數走勢圖' })).toBeInTheDocument();
    expect(container.querySelector('.sentiment-score-line')).not.toBeNull();
    expect(container.querySelector('.sentiment-index-line')).not.toBeNull();
    expect(container.querySelector('table')).toBeNull();

    const hits = container.querySelectorAll('.sentiment-hit');
    await userEvent.hover(hits[1]);
    expect(screen.getByText('2026-09-15')).toBeInTheDocument();
    expect(screen.getByText('33.91 · 恐懼')).toBeInTheDocument();
    expect(screen.getByText('45,511.49')).toBeInTheDocument();
  });

  it('leaves gaps rather than inventing missing breadth values', () => {
    const { container } = render(<SentimentChart rows={[
      day('2026-09-13', 46000, 45),
      day('2026-09-14', 45862.52),
      day('2026-09-15', 45511.49, 33.91),
    ]} market={TW} />);
    expect(container.querySelectorAll('.sentiment-score-line')).toHaveLength(2);
  });

  it('explains the empty sentiment state while retaining the market line', () => {
    const { container } = render(
      <SentimentChart rows={[day('2026-09-15', 45511.49)]} market={TW} />,
    );
    expect(screen.getByText(/漲跌家數同步完成後/)).toBeInTheDocument();
    expect(container.querySelector('.sentiment-score-line')).toBeNull();
    expect(container.querySelector('.sentiment-index-line')).not.toBeNull();
  });
});
