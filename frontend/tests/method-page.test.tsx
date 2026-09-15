import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import MethodPage, { MethodContent } from '../src/pages/MethodPage';

function renderMethodPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><MethodPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('<MethodPage />', () => {
  it('walks through the four derivation steps', () => {
    render(<MethodContent />);
    expect(screen.getByRole('heading', { level: 1, name: '計算原理' })).toBeInTheDocument();
    for (const step of ['位階常態', '量能比與殘差', '近一年百分位', '五級判讀']) {
      expect(screen.getAllByText(new RegExp(step)).length).toBeGreaterThan(0);
    }
    // the regression that everything hangs off
    expect(screen.getByText(/ln\(量能\) = a \+ b × ln\(指數\)/)).toBeInTheDocument();
  });

  it('documents every band edge', () => {
    render(<MethodContent />);
    for (const band of ['≥ 0.8', '0.6 – 0.8', '0.4 – 0.6', '0.2 – 0.4', '≤ 0.2']) {
      expect(screen.getByText(band)).toBeInTheDocument();
    }
  });

  it('explains the drift vs the source spreadsheet', () => {
    render(<MethodContent />);
    expect(screen.getByText(/−7.750181/)).toBeInTheDocument();
    expect(screen.getByText(/每次讀取都用當下的完整歷史重新迴歸/)).toBeInTheDocument();
  });

  it('documents the reproducible sentiment proxy and its five components', () => {
    render(<MethodContent />);
    expect(screen.getByRole('heading', { name: '自算情緒指數' })).toBeInTheDocument();
    expect(screen.getByText(/情緒指數 = 25% × 動能/)).toBeInTheDocument();
    for (const component of ['動能', '距高點回撤', '反向波動率', '市場寬度', '均線偏離']) {
      expect(screen.getAllByText(new RegExp(component)).length).toBeGreaterThan(0);
    }
  });

  it('links back to the readings', () => {
    renderMethodPage();
    expect(screen.getByRole('link', { name: /回市場總覽/ })).toHaveAttribute('href', '/');
  });

  it('shows the raw cold/heat table above the calculation method', async () => {
    const day = {
      date: '2026-09-15', index_close: 45511.49, turnover: 6299,
      expected_turnover: 13867, volume_ratio: .45, residual: -.789,
      percentile: 0, level: 'very_cold', label: '明顯偏冷',
    };
    server.use(http.get('*/api/market/volume-heat', () => (
      HttpResponse.json({ market: 'TW', latest: day, days: [day] })
    )));
    renderMethodPage();
    expect(await screen.findByText('位階常態(億元)')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '冷熱詳細數據' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '計算原理' })).toBeInTheDocument();
  });
});
