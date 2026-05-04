import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/stock-financial';
import { listCards } from '../src/cards/registry';

function renderCard(id: string) {
  const Card = listCards('stock').find((c) => c.id === id)!.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/stock/2330.TW']}>
        <Routes><Route path="/stock/:code" element={<Card />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('IncomeStatementCard', () => {
  it('renders 損益表 with EPS row + annual_summary strip', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/financial', () =>
        HttpResponse.json({
          ticker: '2330.TW', statement: 'income', quarters: 12, ok: true,
          rows: [
            {
              date: '2026-Q1',
              revenue: 50000, gross_profit: 25000,
              operating_income: 18000, net_income: 16000, eps: 6.0,
            },
          ],
          annual_summary: {
            current_4q: { eps: 24.0, revenue: 200000 },
            previous_4q: { eps: 20.0, revenue: 180000 },
            eps_yoy_pct: 20.0,
            revenue_yoy_pct: 11.11,
          },
        }),
      ),
    );
    renderCard('stock-income');
    await waitFor(() => expect(screen.getByText('損益表')).toBeInTheDocument());
    expect(screen.getByText('EPS')).toBeInTheDocument();
    expect(screen.getByText('近 4 季 EPS')).toBeInTheDocument();
    expect(screen.getByText('+20.00%')).toBeInTheDocument();
  });
});

describe('BalanceSheetCard', () => {
  it('renders 資產負債表 title + table rows', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/financial', () =>
        HttpResponse.json({
          ticker: '2330.TW', statement: 'balance', quarters: 12, ok: true,
          rows: [{
            date: '2026-Q1',
            total_assets: 1, total_liabilities: 1,
            total_equity: 1, cash_and_equiv: 1,
          }],
          annual_summary: null,
        }),
      ),
    );
    renderCard('stock-balance');
    await waitFor(() => expect(screen.getByText('資產負債表')).toBeInTheDocument());
    expect(screen.getByText('總資產')).toBeInTheDocument();
  });
});

describe('CashFlowCard', () => {
  it('renders 現金流量表 title', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/financial', () =>
        HttpResponse.json({
          ticker: '2330.TW', statement: 'cashflow', quarters: 12, ok: true,
          rows: [{
            date: '2026-Q1',
            operating_cash_flow: 1, investing_cash_flow: 1,
            financing_cash_flow: 1, free_cash_flow: 1,
          }],
          annual_summary: null,
        }),
      ),
    );
    renderCard('stock-cashflow');
    await waitFor(() => expect(screen.getByText('現金流量表')).toBeInTheDocument());
  });
});
