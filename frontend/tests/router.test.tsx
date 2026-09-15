import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import MarketHeatPage from '../src/pages/MarketHeatPage';
import MethodPage from '../src/pages/MethodPage';

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<MarketHeatPage />} />
          <Route path="/details" element={<MethodPage />} />
          <Route path="/method" element={<Navigate to="/details" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const flow = (date: string, foreignNet: number) => ({
  date,
  dealer_proprietary: { buy: 20, sell: 10, net: 10 },
  dealer_hedge: { buy: 30, sell: 25, net: 5 },
  dealer: { buy: 50, sell: 35, net: 15 },
  trust: { buy: 50, sell: 40, net: 10 },
  foreign: { buy: 200, sell: 200 - foreignNet, net: foreignNet },
  foreign_dealer: { buy: 0, sell: 0, net: 0 },
  total: { buy: 300, sell: 275 - foreignNet, net: 25 + foreignNet },
  turnover_ratio: 10,
});

const day = (date: string, level: string, label: string, percentile: number, foreignNet: number) => ({
  date, index_close: 43119.75, turnover: 8877, expected_turnover: 12209.5,
  volume_ratio: 0.727, residual: -0.319, percentile, level, label,
  institutional: flow(date, foreignNet),
});

function mockApi(requests: string[]) {
  server.use(
    http.get('*/api/market/volume-heat', ({ request }) => {
      requests.push(new URL(request.url).search);
      const days = [
        day('2026-07-30', 'hot', '偏熱', 0.738, 12),
        day('2026-07-31', 'very_cold', '明顯偏冷', 0.042, 80),
      ];
      return HttpResponse.json({ latest: days[days.length - 1], days });
    }),
  );
}

describe('market heat page', () => {
  it('renders the overview charts without the raw detail table at /', async () => {
    const requests: string[] = [];
    mockApi(requests);
    const { container } = renderAt('/');
    // 近一季 is the default range
    expect((await screen.findAllByText('明顯偏冷')).length).toBeGreaterThan(0);
    expect(requests[0]).toBe('?market=TW&days=66');
    expect(screen.getByRole('heading', { name: '自算恐懼貪婪指數 vs 加權指數' })).toBeInTheDocument();
    expect(screen.queryByText('位階常態(億元)')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /查看詳細數據/ })).toHaveAttribute('href', '/details');
    expect(container.querySelector('.sentiment-index-line')).not.toBeNull();
  });

  it('opens the raw cold/heat rows and method from the main heat card', async () => {
    mockApi([]);
    renderAt('/');
    await userEvent.click(await screen.findByRole('link', { name: /查看詳細數據/ }));
    expect(await screen.findByRole('heading', { name: '冷熱詳細數據' })).toBeInTheDocument();
    expect(screen.getByText('位階常態(億元)')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '計算原理' })).toBeInTheDocument();
  });

  it('切換區間 refetches with the chosen days (全部 = no param)', async () => {
    const requests: string[] = [];
    mockApi(requests);
    renderAt('/');
    await screen.findByRole('heading', { name: '自算恐懼貪婪指數 vs 加權指數' });
    await userEvent.click(screen.getByRole('tab', { name: '近一月' }));
    await userEvent.click(screen.getByRole('tab', { name: '全部' }));
    expect(requests).toContain('?market=TW&days=22');
    expect(requests).toContain('?market=TW');
  });

  it('點選組合圖日期會同步切換上方量能與法人資料', async () => {
    mockApi([]);
    const { container } = renderAt('/');
    await screen.findByText('8,877 億');
    expect(container.querySelector('.heat-date')).toHaveTextContent('2026-07-31');
    expect(within(screen.getByLabelText('三大法人摘要')).getByText('+80.00')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '選擇 2026-07-30' }));
    expect(container.querySelector('.heat-date')).toHaveTextContent('2026-07-30');
    expect(within(screen.getByLabelText('三大法人摘要')).getByText('+12.00')).toBeInTheDocument();
  });

  it('redirects unknown paths to /', async () => {
    const requests: string[] = [];
    mockApi(requests);
    renderAt('/nope');
    expect(await screen.findByText('8,877 億')).toBeInTheDocument();
  });
});
