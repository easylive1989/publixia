import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IndexChart, IndexLegend, INSTITUTION_COLORS } from '../src/components/IndexChart';
import type { InstitutionalFlow, MarketHeatDay } from '../src/hooks/useMarketHeat';
import { HEAT_META } from '../src/lib/market-heat';
import { MARKETS } from '../src/lib/markets';

const TW = MARKETS[0];

const flow = (foreign: number, trust: number, dealer: number): InstitutionalFlow => ({
  date: '2026-07-31',
  dealer_proprietary: { buy: 20, sell: 10, net: 10 },
  dealer_hedge: { buy: 30, sell: 30 - (dealer - 10), net: dealer - 10 },
  dealer: { buy: 50, sell: 50 - dealer, net: dealer },
  trust: { buy: 50, sell: 50 - trust, net: trust },
  foreign: { buy: 200, sell: 200 - foreign, net: foreign },
  foreign_dealer: { buy: 0, sell: 0, net: 0 },
  total: { buy: 300, sell: 300 - foreign - trust - dealer, net: foreign + trust + dealer },
  turnover_ratio: 44.01,
});

const days: MarketHeatDay[] = [
  { date: '2026-07-29', index_close: 40039.18, turnover: 11492, expected_turnover: 10837.7, volume_ratio: 1.06, residual: 0.059, percentile: 0.738, level: 'hot', label: '偏熱', institutional: flow(80, -20, 30) },
  { date: '2026-07-30', index_close: 39933.30, turnover: 11469, expected_turnover: 10791.6, volume_ratio: 1.06, residual: 0.061, percentile: 0.738, level: 'hot', label: '偏熱', institutional: flow(-50, 25, -10) },
  { date: '2026-07-31', index_close: 43119.75, turnover: 8877, expected_turnover: 12209.5, volume_ratio: 0.727, residual: -0.319, percentile: 0.042, level: 'very_cold', label: '明顯偏冷', institutional: flow(267.07, 131.01, 163.29) },
];

function chart(onSelectDate = vi.fn()) {
  return render(
    <IndexChart
      days={days}
      market={TW}
      selectedDate="2026-07-31"
      onSelectDate={onSelectDate}
    />,
  );
}

describe('<IndexChart />', () => {
  it('draws one index line, one point per day, and three institutional segments per day', () => {
    const { container } = chart();
    expect(container.querySelectorAll('path.idx-line')).toHaveLength(1);
    expect(container.querySelectorAll('circle.idx-dot')).toHaveLength(3);
    expect(container.querySelectorAll('rect.idx-inst-segment')).toHaveLength(9);
    expect(container.querySelector('circle.idx-dot.selected')).toBeTruthy();
    expect(container.querySelector(`rect[fill="${INSTITUTION_COLORS.foreign}"]`)).toBeTruthy();
  });

  it('uses compact asymmetric limits without distorting the buy and sell scale', () => {
    const { container } = chart();
    const labels = [...container.querySelectorAll('text.tick')].map((node) => node.textContent);
    expect(labels).toContain('+750');
    expect(labels).toContain('−75');

    const zero = container.querySelector('line.idx-zero');
    const top = [...container.querySelectorAll('line.grid')]
      .find((line) => line.getAttribute('y1') === '128');
    const bottom = [...container.querySelectorAll('line.grid')]
      .find((line) => line.getAttribute('y1') === '275');
    const positivePixelsPerBillion = (Number(zero?.getAttribute('y1')) - Number(top?.getAttribute('y1'))) / 750;
    const negativePixelsPerBillion = (Number(bottom?.getAttribute('y1')) - Number(zero?.getAttribute('y1'))) / 75;
    expect(positivePixelsPerBillion).toBeCloseTo(negativePixelsPerBillion, 8);
  });

  it('keeps ordinary heat points and institutional bars easy to see', () => {
    const { container } = chart();
    const dots = [...container.querySelectorAll('circle.idx-dot')];
    expect(Number(dots[0].getAttribute('r'))).toBeGreaterThanOrEqual(2.75);
    expect(dots[2]).toHaveAttribute('r', '5.5');
    expect(Number(container.querySelector('rect.idx-inst-segment')?.getAttribute('width'))).toBeGreaterThanOrEqual(7);
  });

  it('colors each index point with that day heat level and keeps the selected point colored', () => {
    const { container } = chart();
    const dots = [...container.querySelectorAll('circle.idx-dot')];
    expect(dots[0]).toHaveAttribute('fill', HEAT_META.hot.color);
    expect(dots[1]).toHaveAttribute('fill', HEAT_META.hot.color);
    expect(dots[2]).toHaveAttribute('fill', HEAT_META.very_cold.color);
    expect(dots[2]).toHaveClass('selected');
  });

  it('plots a higher index above a lower one', () => {
    const { container } = chart();
    const cy = [...container.querySelectorAll('circle.idx-dot')].map((circle) => Number(circle.getAttribute('cy')));
    expect(cy[2]).toBeLessThan(cy[0]);
    expect(cy[1]).toBeGreaterThan(cy[0]);
  });

  it('hovering a date shows index, heat, and institutional values', async () => {
    const { container } = chart();
    const hits = container.querySelectorAll('rect.idx-hit');
    expect(hits).toHaveLength(3);
    await userEvent.hover(hits[2]);
    expect(screen.getByText('2026-07-31')).toBeInTheDocument();
    expect(screen.getByText('43,119.75')).toBeInTheDocument();
    expect(screen.getByText('明顯偏冷 · PR 4')).toBeInTheDocument();
    expect(screen.getByText('+267.07 億')).toBeInTheDocument();
  });

  it('clicking or pressing Enter selects that trading day', async () => {
    const onSelect = vi.fn();
    const { container } = chart(onSelect);
    const first = container.querySelectorAll('rect.idx-hit')[0];
    await userEvent.click(first);
    expect(onSelect).toHaveBeenCalledWith('2026-07-29');
    await userEvent.type(first, '{Enter}');
    expect(onSelect).toHaveBeenLastCalledWith('2026-07-29');
  });

  it('renders nothing for an empty range', () => {
    const { container } = render(
      <IndexChart days={[]} market={TW} selectedDate="" onSelectDate={() => {}} />,
    );
    expect(container.querySelector('svg')).toBeNull();
  });

  it('legend names the line and all three institutions', () => {
    render(<IndexLegend market={TW} />);
    for (const label of [
      '加權指數', '明顯偏冷', '偏冷', '正常', '偏熱', '明顯偏熱',
      '外資', '投信', '自營商', '零軸上方為買超，下方為賣超',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });
});
