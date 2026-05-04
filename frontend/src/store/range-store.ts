import { create } from 'zustand';

const STORAGE_KEY = 'sd_dashboard_range';

export const RANGES = ['1M', '3M', '6M', '1Y', '3Y'] as const;
export type RangeKey = (typeof RANGES)[number];

const DEFAULT_RANGE: RangeKey = '3M';

function loadInitial(): RangeKey {
  const raw = localStorage.getItem(STORAGE_KEY);
  return (RANGES as readonly string[]).includes(raw ?? '')
    ? (raw as RangeKey)
    : DEFAULT_RANGE;
}

interface RangeStore {
  range: RangeKey;
  setRange: (r: RangeKey) => void;
}

export const useRangeStore = create<RangeStore>((set) => ({
  range: loadInitial(),
  setRange: (range) => {
    localStorage.setItem(STORAGE_KEY, range);
    set({ range });
  },
}));
