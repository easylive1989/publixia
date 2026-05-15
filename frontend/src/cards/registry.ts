import type { FC } from 'react';

export type CardPage = 'dashboard' | 'stock';

export interface CardSpec {
  id: string;
  label: string;
  defaultPage: CardPage;
  component: FC;
  cols?: 1 | 2 | 3;
  rows?: 1 | 2;
}

let _registry: CardSpec[] = [];

export function registerCard(spec: CardSpec): void {
  if (_registry.some(c => c.id === spec.id)) {
    throw new Error(`Card already registered: ${spec.id}`);
  }
  _registry.push(spec);
}

export function listCards(page: CardPage): CardSpec[] {
  return _registry.filter(c => c.defaultPage === page);
}

export function getCard(id: string): CardSpec | undefined {
  return _registry.find(c => c.id === id);
}

// Test-only: clear all registrations.
export function _reset(): void {
  _registry = [];
}
