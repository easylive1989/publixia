import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import MarketHeatPage from '../src/pages/MarketHeatPage';

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<MarketHeatPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const day = (date: string, level: string, label: string, percentile: number) => ({
  date, taiex_close: 43119.75, turnover: 8877, expected_turnover: 12209.5,
  volume_ratio: 0.727, residual: -0.319, percentile, level, label,
});

function mockApi(requests: string[]) {
  server.use(
    http.get('*/api/market/volume-heat', ({ request }) => {
      requests.push(new URL(request.url).search);
      const days = [
        day('2026-07-30', 'hot', '偏熱', 0.738),
        day('2026-07-31', 'very_cold', '明顯偏冷', 0.042),
      ];
      return HttpResponse.json({ latest: days[days.length - 1], days });
    }),
  );
}

describe('market heat page', () => {
  it('renders 今日判讀 + sheet 比較表 at /', async () => {
    const requests: string[] = [];
    mockApi(requests);
    renderAt('/');
    // 近一年 is the default range
    expect((await screen.findAllByText('明顯偏冷')).length).toBeGreaterThan(0);
    expect(requests[0]).toBe('?days=240');
    // sheet-style table: headers + newest-first rows + 判讀 values
    expect(screen.getByText('位階常態(億元)')).toBeInTheDocument();
    // 近一年百分位 appears in the today card (dt) and the table header (th)
    expect(screen.getAllByText('近一年百分位').length).toBe(2);
    const cells = screen.getAllByRole('cell').map((c) => c.textContent);
    expect(cells).toContain('0.042');
    expect(cells).toContain('43,119.75');
    const rows = screen.getAllByRole('row');
    expect(rows[1].textContent).toContain('2026-07-31'); // newest first
  });

  it('切換區間 refetches with the chosen days (全部 = no param)', async () => {
    const requests: string[] = [];
    mockApi(requests);
    renderAt('/');
    await screen.findByText('位階常態(億元)');
    await userEvent.click(screen.getByRole('tab', { name: '近一月' }));
    await userEvent.click(screen.getByRole('tab', { name: '全部' }));
    expect(requests).toContain('?days=22');
    expect(requests).toContain('');
  });

  it('redirects unknown paths to /', async () => {
    const requests: string[] = [];
    mockApi(requests);
    renderAt('/nope');
    expect(await screen.findByText('位階常態(億元)')).toBeInTheDocument();
  });
});
