import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InstitutionalFlowPanel } from '../src/components/InstitutionalFlow';
import type { InstitutionalFlow, MarketHeatDay } from '../src/hooks/useMarketHeat';

const institutional: InstitutionalFlow = {
  date: '2026-09-01',
  dealer_proprietary: { buy: 158.31, sell: 126.74, net: 31.57 },
  dealer_hedge: { buy: 469.08, sell: 337.35, net: 131.73 },
  dealer: { buy: 627.39, sell: 464.09, net: 163.30 },
  trust: { buy: 391.06, sell: 260.05, net: 131.01 },
  foreign: { buy: 4019.99, sell: 3752.91, net: 267.08 },
  foreign_dealer: { buy: 0, sell: 0, net: 0 },
  total: { buy: 5038.46, sell: 4477.07, net: 561.39 },
  turnover_ratio: 44.01,
};

const day = (date: string, flow: InstitutionalFlow | null = institutional): MarketHeatDay => ({
  date,
  index_close: 24016.78,
  turnover: 10810,
  expected_turnover: 10000,
  volume_ratio: 1.08,
  residual: .07,
  percentile: .62,
  level: 'hot',
  label: '偏熱',
  institutional: flow,
});

describe('<InstitutionalFlowPanel />', () => {
  it('shows official rows, total, and turnover ratio', () => {
    const rows = [day('2026-08-31'), day('2026-09-01')];
    render(<InstitutionalFlowPanel day={rows[1]} rows={rows} onSelectDate={() => {}} />);
    expect(screen.getByText('115.09.01（二）')).toBeInTheDocument();
    for (const label of ['自營商（自行買賣）', '自營商（避險）', '投信', '外資及陸資', '外資自營商', '合計']) {
      expect(screen.getAllByText(label).length).toBeGreaterThanOrEqual(1);
    }
    expect(screen.getAllByText('+561.39').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('44.01%')).toBeInTheDocument();
  });

  it('date arrows select adjacent rows and respect bounds', async () => {
    const rows = [day('2026-08-31'), day('2026-09-01')];
    const onSelect = vi.fn();
    render(<InstitutionalFlowPanel day={rows[1]} rows={rows} onSelectDate={onSelect} />);
    await userEvent.click(screen.getByRole('button', { name: '前一個交易日' }));
    expect(onSelect).toHaveBeenCalledWith('2026-08-31');
    expect(screen.getByRole('button', { name: '後一個交易日' })).toBeDisabled();
  });

  it('shows a clear backfill state when the selected day has no flow yet', () => {
    const missing = day('2026-08-31', null);
    render(<InstitutionalFlowPanel day={missing} rows={[missing]} onSelectDate={() => {}} />);
    expect(screen.getByText(/法人資料尚未同步/)).toBeInTheDocument();
  });
});
