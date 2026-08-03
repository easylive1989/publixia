import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IndexChart, IndexLegend } from '../src/components/IndexChart';
import type { MarketHeatDay } from '../src/hooks/useMarketHeat';
import { HEAT_META } from '../src/lib/market-heat';

const days: MarketHeatDay[] = [
  { date: '2026-07-29', taiex_close: 40039.18, turnover: 11492, expected_turnover: 10837.7, volume_ratio: 1.06, residual: 0.059, percentile: 0.738, level: 'hot', label: '偏熱' },
  { date: '2026-07-30', taiex_close: 39933.30, turnover: 11469, expected_turnover: 10791.6, volume_ratio: 1.06, residual: 0.061, percentile: 0.738, level: 'hot', label: '偏熱' },
  { date: '2026-07-31', taiex_close: 43119.75, turnover: 8877, expected_turnover: 12209.5, volume_ratio: 0.727, residual: -0.319, percentile: 0.042, level: 'very_cold', label: '明顯偏冷' },
];

describe('<IndexChart />', () => {
  it('draws one index line and one 判讀-colored dot per day', () => {
    const { container } = render(<IndexChart days={days} />);
    expect(container.querySelectorAll('path.idx-line')).toHaveLength(1);
    const dots = container.querySelectorAll('circle.idx-dot');
    expect(dots).toHaveLength(3);
    expect(dots[2].getAttribute('fill')).toBe(HEAT_META.very_cold.color);
    expect(dots[0].getAttribute('fill')).toBe(HEAT_META.hot.color);
  });

  it('plots a higher index above a lower one', () => {
    const { container } = render(<IndexChart days={days} />);
    const cy = [...container.querySelectorAll('circle.idx-dot')].map((c) => Number(c.getAttribute('cy')));
    // 2026-07-31 has the highest close → smallest y (SVG y grows downward)
    expect(cy[2]).toBeLessThan(cy[0]);
    expect(cy[1]).toBeGreaterThan(cy[0]); // 07-30 is the lowest close
  });

  it('hovering a point shows its index and 判讀', async () => {
    const { container } = render(<IndexChart days={days} />);
    const hits = container.querySelectorAll('svg rect[fill="transparent"]');
    expect(hits).toHaveLength(3);
    await userEvent.hover(hits[2]);
    expect(screen.getByText('2026-07-31')).toBeInTheDocument();
    expect(screen.getByText('43,119.75')).toBeInTheDocument();
    expect(screen.getByText('明顯偏冷')).toBeInTheDocument();
  });

  it('renders nothing for an empty range', () => {
    const { container } = render(<IndexChart days={[]} />);
    expect(container.querySelector('svg')).toBeNull();
  });

  it('legend names the line and every band', () => {
    render(<IndexLegend />);
    for (const zh of ['加權指數', '明顯偏熱', '偏熱', '正常', '偏冷', '明顯偏冷']) {
      expect(screen.getByText(zh)).toBeInTheDocument();
    }
  });
});
