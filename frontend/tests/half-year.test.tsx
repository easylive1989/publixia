import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import MarketHeatPage from '../src/pages/MarketHeatPage';
import {
  filterHalfYear,
  halfYearLabel,
  halfYearOf,
  halfYearOptions,
  halfYearValue,
  parseHalfYear,
} from '../src/lib/half-year';

describe('half-year helpers', () => {
  it('maps a date to its half and back to a label', () => {
    expect(halfYearOf('2025-06-30')).toEqual({ year: 2025, half: 1 });
    expect(halfYearOf('2025-07-01')).toEqual({ year: 2025, half: 2 });
    expect(halfYearLabel({ year: 2025, half: 2 })).toBe('2025 下');
    expect(halfYearLabel({ year: 2026, half: 1 })).toBe('2026 上');
  });

  it('round-trips the option value', () => {
    expect(halfYearValue({ year: 2026, half: 1 })).toBe('2026H1');
    expect(parseHalfYear('2026H1')).toEqual({ year: 2026, half: 1 });
    expect(parseHalfYear('')).toBeNull();
    expect(parseHalfYear('2026H3')).toBeNull();
  });

  it('lists halves newest-first and stops at the latest data half', () => {
    const opts = halfYearOptions('2026-03-10', 2024).map(halfYearLabel);
    expect(opts).toEqual(['2026 上', '2025 下', '2025 上', '2024 下', '2024 上']);
    // 資料已進到下半年時，該年兩個半年都列出來
    expect(halfYearOptions('2026-07-31', 2025).map(halfYearLabel)).toEqual([
      '2026 下', '2026 上', '2025 下', '2025 上',
    ]);
  });

  it('filters rows to the selected half, bounds inclusive', () => {
    const rows = ['2024-12-31', '2025-01-02', '2025-06-30', '2025-07-01'].map((date) => ({ date }));
    expect(filterHalfYear(rows, { year: 2025, half: 1 }).map((r) => r.date))
      .toEqual(['2025-01-02', '2025-06-30']);
    expect(filterHalfYear(rows, { year: 2025, half: 2 }).map((r) => r.date))
      .toEqual(['2025-07-01']);
  });
});

const day = (date: string) => ({
  date, taiex_close: 43119.75, turnover: 8877, expected_turnover: 12209.5,
  volume_ratio: 0.727, residual: -0.319, percentile: 0.042,
  level: 'very_cold', label: '明顯偏冷',
});

const HISTORY = ['2025-06-30', '2025-08-01', '2026-01-02', '2026-07-31'].map(day);

function renderPage(requests: string[]) {
  server.use(
    http.get('*/api/market/volume-heat', ({ request }) => {
      const search = new URL(request.url).search;
      requests.push(search);
      // 近 N 日的請求只回最後一筆，全歷史回全部 —— 讓「有沒有抓全歷史」看得出來
      const days = search ? HISTORY.slice(-1) : HISTORY;
      return HttpResponse.json({ latest: HISTORY[HISTORY.length - 1], days });
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/']}>
        <Routes><Route path="/" element={<MarketHeatPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('半年區間 dropdown', () => {
  it('選半年會抓全歷史並只留該半年的交易日', async () => {
    const requests: string[] = [];
    renderPage(requests);
    await screen.findByText('位階常態(億元)');

    await userEvent.selectOptions(screen.getByLabelText('半年區間'), '2025H2');
    expect(requests).toContain('');   // 全歷史（沒有 days 參數）

    const dates = await screen.findAllByText(/^2025-08-01$/);
    expect(dates.length).toBeGreaterThan(0);
    expect(screen.queryByText('2026-07-31')).not.toBeInTheDocument();
    expect(screen.queryByText('2025-06-30')).not.toBeInTheDocument();
  });

  it('選半年時區間 tab 不亮，切回 tab 會清掉半年選擇', async () => {
    const requests: string[] = [];
    renderPage(requests);
    await screen.findByText('位階常態(億元)');
    expect(screen.getByRole('tab', { name: '近一季' })).toHaveAttribute('aria-selected', 'true');

    const select = screen.getByLabelText('半年區間') as HTMLSelectElement;
    await userEvent.selectOptions(select, '2025H2');
    expect(screen.getByRole('tab', { name: '近一季' })).toHaveAttribute('aria-selected', 'false');

    await userEvent.click(screen.getByRole('tab', { name: '近一月' }));
    expect(select.value).toBe('');
    expect(screen.getByRole('tab', { name: '近一月' })).toHaveAttribute('aria-selected', 'true');
    expect(requests).toContain('?days=22');
  });

  it('選項到最新資料所在的半年為止', async () => {
    renderPage([]);
    await screen.findByText('位階常態(億元)');
    const labels = Array.from(
      (screen.getByLabelText('半年區間') as HTMLSelectElement).options,
    ).map((o) => o.textContent);
    expect(labels[0]).toBe('半年區間…');
    expect(labels[1]).toBe('2026 下半年');
    expect(labels[2]).toBe('2026 上半年');
    expect(labels[labels.length - 1]).toBe('2016 上半年');
  });
});
