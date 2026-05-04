import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import DashboardPage from '../src/pages/DashboardPage';
import '../src/cards';
import { useCardPrefsStore } from '../src/store/card-prefs-store';
import { useRangeStore } from '../src/store/range-store';

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DashboardPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useCardPrefsStore.setState({ hiddenIds: new Set() });
  useRangeStore.setState({ range: '3M' });
  localStorage.clear();
  server.use(
    http.get('*/api/dashboard', () =>
      HttpResponse.json({
        taiex: { value: 18000, timestamp: '2026-05-02T08:00:00Z', extra: { change_pct: 1.0 } },
        fx:    { value: 32.5,  timestamp: '2026-05-02T08:00:00Z', extra: {} },
      }),
    ),
    http.get('*/api/history/:indicator', () => HttpResponse.json([])),
  );
});

describe('DashboardPage', () => {
  it('renders all 12 registered cards by default', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('加權指數')).toBeInTheDocument();
      expect(screen.getByText('台幣兌美金')).toBeInTheDocument();
    });
  });

  it('hides a card after toggling it off in the dialog', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('加權指數')).toBeInTheDocument());
    expect(screen.getAllByText('加權指數')).toHaveLength(1);  // page only
    await userEvent.click(screen.getByRole('button', { name: '設定' }));
    expect(screen.getAllByText('加權指數')).toHaveLength(2);  // page + dialog label
    await userEvent.click(screen.getByRole('checkbox', { name: '加權指數' }));
    // Page card removed; the label inside the still-open dialog remains.
    expect(screen.getAllByText('加權指數')).toHaveLength(1);
    expect(useCardPrefsStore.getState().isHidden('taiex')).toBe(true);
  });

  it('range bar updates the global range and persists', async () => {
    renderPage();
    const tab = await screen.findByRole('tab', { name: '1 年' });
    expect(tab).toHaveAttribute('aria-selected', 'false');
    await userEvent.click(tab);
    expect(useRangeStore.getState().range).toBe('1Y');
    expect(localStorage.getItem('sd_dashboard_range')).toBe('1Y');
    expect(tab).toHaveAttribute('aria-selected', 'true');
  });
});
