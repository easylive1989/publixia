import { describe, it, expect, beforeEach } from 'vitest';
import { useCardPrefsStore } from '../src/store/card-prefs-store';

describe('card-prefs-store', () => {
  beforeEach(() => {
    localStorage.clear();
    useCardPrefsStore.setState({ hiddenIds: new Set() });
  });

  it('toggle adds an id, second toggle removes it', () => {
    useCardPrefsStore.getState().toggle('taiex');
    expect(useCardPrefsStore.getState().isHidden('taiex')).toBe(true);
    useCardPrefsStore.getState().toggle('taiex');
    expect(useCardPrefsStore.getState().isHidden('taiex')).toBe(false);
  });

  it('toggle persists to localStorage as JSON array', () => {
    useCardPrefsStore.getState().toggle('fx');
    const raw = localStorage.getItem('sd_card_prefs');
    expect(JSON.parse(raw!)).toEqual(['fx']);
  });

  it('multiple toggles persist all hidden ids', () => {
    useCardPrefsStore.getState().toggle('taiex');
    useCardPrefsStore.getState().toggle('fx');
    const raw = localStorage.getItem('sd_card_prefs');
    expect(new Set(JSON.parse(raw!))).toEqual(new Set(['taiex', 'fx']));
  });
});
