import { describe, it, expect, beforeEach } from 'vitest';
import { registerCard, listCards, getCard, _reset } from '../src/cards/registry';

const Stub = () => null;

describe('card registry', () => {
  beforeEach(() => {
    _reset();
  });

  it('register and list cards by page', () => {
    registerCard({ id: 'a', label: 'A', defaultPage: 'dashboard', component: Stub });
    registerCard({ id: 'b', label: 'B', defaultPage: 'stock', component: Stub });
    expect(listCards('dashboard').map(c => c.id)).toEqual(['a']);
    expect(listCards('stock').map(c => c.id)).toEqual(['b']);
  });

  it('getCard returns spec by id', () => {
    registerCard({ id: 'x', label: 'X', defaultPage: 'dashboard', component: Stub });
    expect(getCard('x')?.label).toBe('X');
    expect(getCard('nope')).toBeUndefined();
  });

  it('duplicate id throws', () => {
    registerCard({ id: 'dup', label: 'D', defaultPage: 'dashboard', component: Stub });
    expect(() =>
      registerCard({ id: 'dup', label: 'D2', defaultPage: 'dashboard', component: Stub })
    ).toThrow(/already registered/);
  });

  it('cols defaults to undefined; explicit cols preserved', () => {
    registerCard({ id: 'one', label: 'One', defaultPage: 'dashboard', component: Stub });
    registerCard({ id: 'three', label: 'Three', defaultPage: 'dashboard', component: Stub, cols: 3 });
    const list = listCards('dashboard');
    expect(list.find(c => c.id === 'one')?.cols).toBeUndefined();
    expect(list.find(c => c.id === 'three')?.cols).toBe(3);
  });
});
