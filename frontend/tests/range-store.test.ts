import { describe, it, expect, beforeEach } from 'vitest';
import { useRangeStore } from '../src/store/range-store';

describe('range-store', () => {
  beforeEach(() => {
    localStorage.clear();
    useRangeStore.setState({ range: '3M' });
  });

  it('defaults to 3M', () => {
    expect(useRangeStore.getState().range).toBe('3M');
  });

  it('setRange updates state and persists to localStorage', () => {
    useRangeStore.getState().setRange('1Y');
    expect(useRangeStore.getState().range).toBe('1Y');
    expect(localStorage.getItem('sd_dashboard_range')).toBe('1Y');
  });
});
