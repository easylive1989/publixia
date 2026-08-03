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
    expect(screen.getByText(/ln\(成交金額\) = a \+ b × ln\(加權指數\)/)).toBeInTheDocument();
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
