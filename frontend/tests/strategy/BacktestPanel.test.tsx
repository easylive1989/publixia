import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '../setup';
import { BacktestPanel } from '../../src/components/strategy/BacktestPanel';

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>{node}</QueryClientProvider>
  );
}

describe('BacktestPanel', () => {
  it('renders the date range form + run button', () => {
    render(wrap(<BacktestPanel strategyId={1} />));
    expect(screen.getByLabelText(/開始日期/)).toBeInTheDocument();
    expect(screen.getByLabelText(/結束日期/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /執行回測/ })).toBeInTheDocument();
  });

  it('runs a backtest and renders summary + trades on success', async () => {
    server.use(
      http.post('*/api/strategies/1/backtest', () =>
        HttpResponse.json({
          trades: [{
            entry_date: '2026-02-01', entry_price: 17000,
            exit_date:  '2026-02-10', exit_price:  17200,
            exit_reason: 'TAKE_PROFIT', held_bars: 7,
            pnl_points: 200, pnl_amount: 40000, from_stop: false,
          }],
          summary: {
            total_pnl_amount: 40000, win_rate: 100,
            avg_win_points: 200, avg_loss_points: 0,
            profit_factor: 0, max_drawdown_amt: 0,
            max_drawdown_pct: 0, n_trades: 1, avg_held_bars: 7,
          },
          warnings: [],
        }),
      ),
    );
    render(wrap(<BacktestPanel strategyId={1} />));
    fireEvent.click(screen.getByRole('button', { name: /執行回測/ }));
    await waitFor(() =>
      expect(screen.getByText(/總損益/)).toBeInTheDocument(),
    );
    expect(screen.getByText('TAKE_PROFIT')).toBeInTheDocument();
  });

  it('renders warnings when the API returns them', async () => {
    server.use(
      http.post('*/api/strategies/1/backtest', () =>
        HttpResponse.json({
          trades: [],
          summary: {
            total_pnl_amount: 0, win_rate: 0,
            avg_win_points: 0, avg_loss_points: 0,
            profit_factor: 0, max_drawdown_amt: 0,
            max_drawdown_pct: 0, n_trades: 0, avg_held_bars: 0,
          },
          warnings: ['no bars in futures_daily for contract=TX between 2026-01-01 and 2026-02-01'],
        }),
      ),
    );
    render(wrap(<BacktestPanel strategyId={1} />));
    fireEvent.click(screen.getByRole('button', { name: /執行回測/ }));
    await waitFor(() =>
      expect(screen.getByText(/no bars in futures_daily/)).toBeInTheDocument(),
    );
  });
});
