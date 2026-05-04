import { create } from 'zustand';

const STORAGE_KEY = 'sd_card_prefs';

function loadInitial(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    return new Set(Array.isArray(arr) ? arr : []);
  } catch {
    return new Set();
  }
}

function persist(ids: Set<string>): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(ids)));
}

interface CardPrefsStore {
  hiddenIds: Set<string>;
  toggle: (id: string) => void;
  isHidden: (id: string) => boolean;
}

export const useCardPrefsStore = create<CardPrefsStore>((set, get) => ({
  hiddenIds: loadInitial(),
  toggle: (id: string) => {
    const next = new Set(get().hiddenIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    persist(next);
    set({ hiddenIds: next });
  },
  isHidden: (id: string) => get().hiddenIds.has(id),
}));
