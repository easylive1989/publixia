import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MethodPage from '../src/pages/MethodPage';

describe('<MethodPage />', () => {
  it('walks through the four derivation steps', () => {
    render(<MemoryRouter><MethodPage /></MemoryRouter>);
    expect(screen.getByRole('heading', { level: 1, name: '計算原理' })).toBeInTheDocument();
    for (const step of ['位階常態', '量能比與殘差', '近一年百分位', '五級判讀']) {
      expect(screen.getAllByText(new RegExp(step)).length).toBeGreaterThan(0);
    }
    // the regression that everything hangs off
    expect(screen.getByText(/ln\(量能\) = a \+ b × ln\(指數\)/)).toBeInTheDocument();
  });

  it('explains how the same method carries over to Nasdaq', () => {
    render(<MemoryRouter><MethodPage /></MemoryRouter>);
    expect(screen.getByRole('heading', { name: /套用在 Nasdaq/ })).toBeInTheDocument();
    // 為什麼配這一組指數與量能
    expect(screen.getAllByText(/composite volume/).length).toBeGreaterThan(0);
    // 股數 vs 金額：殘差幾乎不受影響
    expect(screen.getByText(/ln\(成交金額\) ≈ ln\(成交股數\) \+ ln\(成交均價\)/)).toBeInTheDocument();
    // 判讀語意在美股會反過來，這一條不能漏
    expect(screen.getByText(/放量最常出現在恐慌下殺/)).toBeInTheDocument();
    // Nasdaq 沒有盤中判讀
    expect(screen.getByText(/沒有盤中判讀/)).toBeInTheDocument();
  });

  it('documents every band edge', () => {
    render(<MemoryRouter><MethodPage /></MemoryRouter>);
    for (const band of ['≥ 0.8', '0.6 – 0.8', '0.4 – 0.6', '0.2 – 0.4', '≤ 0.2']) {
      expect(screen.getByText(band)).toBeInTheDocument();
    }
  });

  it('explains the drift vs the source spreadsheet', () => {
    render(<MemoryRouter><MethodPage /></MemoryRouter>);
    expect(screen.getByText(/−7.750181/)).toBeInTheDocument();
    expect(screen.getByText(/每次讀取都用當下的完整歷史重新迴歸/)).toBeInTheDocument();
  });

  it('links back to the readings', () => {
    render(<MemoryRouter><MethodPage /></MemoryRouter>);
    expect(screen.getByRole('link', { name: /回判讀/ })).toHaveAttribute('href', '/');
  });
});
