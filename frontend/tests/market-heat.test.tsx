import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MarketHeat } from '../src/components/MarketHeat';
import type { MarketHeatDay, MarketHeatPayload } from '../src/hooks/useMarketHeat';
import { HEAT_META, fmtBillion, fmtPercentile } from '../src/lib/market-heat';

function day(over: Partial<MarketHeatDay>): MarketHeatDay {
  return {
    date: '2026-07-31', taiex_close: 43119.75, turnover: 8877,
    expected_turnover: 12209.5, volume_ratio: 0.727, residual: -0.3188,
    percentile: 0.042, level: 'very_cold', label: '明顯偏冷',
    ...over,
  };
}

const payload: MarketHeatPayload = {
  latest: day({}),
  days: [
    day({ date: '2026-07-29', turnover: 11492, volume_ratio: 1.06, percentile: 0.738, level: 'hot', label: '偏熱' }),
    day({ date: '2026-07-30', turnover: 11469, volume_ratio: 1.06, percentile: 0.738, level: 'hot', label: '偏熱' }),
    day({}),
  ],
};

describe('market heat helpers', () => {
  it('formats 億元 and percentile like the sheet', () => {
    expect(fmtBillion(12209.52178)).toBe('12,210');
    expect(fmtPercentile(0.042)).toBe('PR 4');
  });

  it('has metadata for all five 判讀 levels', () => {
    expect(HEAT_META.very_cold.zh).toBe('明顯偏冷');
    expect(HEAT_META.very_hot.zh).toBe('明顯偏熱');
    expect(HEAT_META.normal.zh).toBe('正常');
  });
});

describe('<MarketHeat />', () => {
  it('shows the latest 判讀 with its stats', () => {
    render(<MarketHeat data={payload} isLoading={false} />);
    // 判讀 shows in the badge and again in the legend
    expect(screen.getAllByText('明顯偏冷')).toHaveLength(2);
    expect(screen.getByText('2026-07-31')).toBeInTheDocument();
    expect(screen.getByText('8,877 億')).toBeInTheDocument();     // 成交金額
    expect(screen.getByText('12,210 億')).toBeInTheDocument();    // 位階常態
    expect(screen.getByText('×0.73')).toBeInTheDocument();        // 量能比
    expect(screen.getByText('PR 4')).toBeInTheDocument();         // 百分位
  });

  it('legend names every band so color is never alone', () => {
    render(<MarketHeat data={payload} isLoading={false} />);
    for (const zh of ['明顯偏熱', '偏熱', '正常', '偏冷', '明顯偏冷', '位階常態']) {
      expect(screen.getAllByText(zh).length).toBeGreaterThanOrEqual(1);
    }
  });

  it('hovering a day reveals its tooltip', async () => {
    const { container } = render(<MarketHeat data={payload} isLoading={false} />);
    const hits = container.querySelectorAll('svg rect[fill="transparent"]');
    expect(hits).toHaveLength(3);
    await userEvent.hover(hits[0]);
    expect(screen.getByText('2026-07-29')).toBeInTheDocument();
    expect(screen.getAllByText('偏熱').length).toBeGreaterThan(1); // legend + tooltip
  });

  it('empty payload renders the syncing note, not a crash', () => {
    render(<MarketHeat data={{ latest: null, days: [] }} isLoading={false} />);
    expect(screen.getByText(/大盤資料同步中/)).toBeInTheDocument();
  });
});

describe('<HeatTable />', () => {
  it('mirrors the sheet columns, newest first', async () => {
    const { HeatTable } = await import('../src/components/HeatTable');
    render(<HeatTable rows={payload.days} />);
    for (const h of ['日期', '加權指數', '成交金額(億元)', '位階常態(億元)', '量能比', '殘差', '近一年百分位', '判讀']) {
      expect(screen.getByText(h)).toBeInTheDocument();
    }
    const rows = screen.getAllByRole('row');
    expect(rows).toHaveLength(1 + payload.days.length);
    expect(rows[1].textContent).toContain('2026-07-31');       // newest first
    expect(rows[1].textContent).toContain('明顯偏冷');          // 判讀 badge
    expect(rows[1].textContent).toContain('-0.319');           // 殘差 3dp
    expect(rows[1].textContent).toContain('0.042');            // 百分位 as sheet
  });

  it('renders nothing for an empty range', async () => {
    const { HeatTable } = await import('../src/components/HeatTable');
    const { container } = render(<HeatTable rows={[]} />);
    expect(container.querySelector('table')).toBeNull();
  });
});
