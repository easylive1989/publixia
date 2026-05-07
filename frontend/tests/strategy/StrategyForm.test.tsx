import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StrategyForm } from '../../src/components/strategy/StrategyForm';
import type { DslSchema } from '../../src/hooks/useStrategy';

const SCHEMA: DslSchema = {
  version: 1,
  fields: ['close', 'high', 'low'],
  operators: ['gt', 'lt'],
  indicators: [
    { name: 'sma', params: [{ name: 'n', type: 'int', min: 1, default: 20 }] },
  ],
  exit_modes: ['pct', 'points', 'dsl'],
  vars: ['entry_price'],
};

describe('StrategyForm', () => {
  it('renders all required metadata inputs in create mode', () => {
    render(
      <StrategyForm
        schema={SCHEMA}
        mode="create"
        onSubmit={() => {}}
      />,
    );
    expect(screen.getByLabelText(/名稱/)).toBeInTheDocument();
    expect(screen.getByLabelText(/方向/)).toBeInTheDocument();
    expect(screen.getByLabelText(/商品/)).toBeInTheDocument();
    expect(screen.getByLabelText(/口數/)).toBeInTheDocument();
  });

  it('blocks submit with empty name in create mode', () => {
    const calls: unknown[] = [];
    render(
      <StrategyForm
        schema={SCHEMA}
        mode="create"
        onSubmit={(v) => calls.push(v)}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /儲存/ }));
    expect(calls.length).toBe(0);
    expect(screen.getByText(/請輸入名稱/)).toBeInTheDocument();
  });

  it('emits a payload with sensible defaults on first submit', () => {
    const calls: unknown[] = [];
    render(
      <StrategyForm
        schema={SCHEMA}
        mode="create"
        onSubmit={(v) => calls.push(v)}
      />,
    );
    fireEvent.change(screen.getByLabelText(/名稱/), { target: { value: 's1' } });
    fireEvent.click(screen.getByRole('button', { name: /新增條件/ }));
    fireEvent.click(screen.getByRole('button', { name: /儲存/ }));
    expect(calls).toHaveLength(1);
    const payload = calls[0] as Record<string, unknown>;
    expect(payload.name).toBe('s1');
    expect(payload.contract).toBe('TX');
    expect(payload.contract_size).toBe(1);
  });

  it('freezes DSL fields when initial.state != idle (edit mode)', () => {
    render(
      <StrategyForm
        schema={SCHEMA}
        mode="edit"
        initial={{
          name: 'in_pos', direction: 'long', contract: 'TX',
          contract_size: 1, max_hold_days: null,
          entry_dsl: { version: 1, all: [
            { left: { field: 'close' }, op: 'gt', right: { const: 100 } },
          ]},
          take_profit_dsl: { version: 1, type: 'pct', value: 2.0 },
          stop_loss_dsl:   { version: 1, type: 'pct', value: 1.0 },
          state: 'open',
        }}
        onSubmit={() => {}}
      />,
    );
    expect(screen.getByText(/在場內,條件已凍結/)).toBeInTheDocument();
  });
});
