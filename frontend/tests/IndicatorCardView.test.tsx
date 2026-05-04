import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IndicatorCardView } from '../src/components/IndicatorCardView';

describe('IndicatorCardView', () => {
  it('renders title, value, sub, and badge', () => {
    render(
      <IndicatorCardView
        title="加權指數"
        value="18,000"
        sub="前收 17,800 · 更新 2026-05-02"
        badge={{ text: '+1.20%', tone: 'up' }}
      />,
    );
    expect(screen.getByText('加權指數')).toBeInTheDocument();
    expect(screen.getByText('18,000')).toBeInTheDocument();
    expect(screen.getByText('前收 17,800 · 更新 2026-05-02')).toBeInTheDocument();
    expect(screen.getByText('+1.20%')).toBeInTheDocument();
  });

  it('shows loading state', () => {
    render(<IndicatorCardView title="X" loading />);
    expect(screen.getByText('載入中…')).toBeInTheDocument();
  });

  it('shows error state when error string present', () => {
    render(<IndicatorCardView title="X" error="無法載入" />);
    expect(screen.getByText('無法載入')).toBeInTheDocument();
  });

  it('applies valueClass for up/down coloring', () => {
    render(
      <IndicatorCardView title="外資" value="+10.50 億" valueClass="text-green-600" />,
    );
    expect(screen.getByText('+10.50 億')).toHaveClass('text-green-600');
  });

  it('renders a sparkline when series has 2 or more points', () => {
    render(
      <IndicatorCardView
        title="X"
        value="100"
        series={[
          { timestamp: '2026-04-01T00:00:00Z', value: 90 },
          { timestamp: '2026-04-02T00:00:00Z', value: 100 },
        ]}
      />,
    );
    expect(screen.getByTestId('spark')).toBeInTheDocument();
  });

  it('omits sparkline when series is missing or has fewer than 2 points', () => {
    const { rerender } = render(<IndicatorCardView title="X" value="100" />);
    expect(screen.queryByTestId('spark')).toBeNull();
    rerender(
      <IndicatorCardView
        title="X"
        value="100"
        series={[{ timestamp: '2026-04-01T00:00:00Z', value: 90 }]}
      />,
    );
    expect(screen.queryByTestId('spark')).toBeNull();
  });
});
