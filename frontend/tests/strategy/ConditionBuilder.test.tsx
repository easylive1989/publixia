import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConditionBuilder } from '../../src/components/strategy/ConditionBuilder';
import type { DslSchema } from '../../src/hooks/useStrategy';

const SCHEMA: DslSchema = {
  version: 1,
  fields: ['close', 'high', 'low'],
  operators: ['gt', 'lt', 'cross_above', 'streak_above'],
  indicators: [
    { name: 'sma', params: [{ name: 'n', type: 'int', min: 1 }] },
  ],
  exit_modes: ['pct', 'points', 'dsl'],
  vars: ['entry_price'],
};

describe('ConditionBuilder', () => {
  it('renders an empty list with an "add condition" button when value is empty', () => {
    render(
      <ConditionBuilder schema={SCHEMA} value={[]} onChange={() => {}} />,
    );
    expect(screen.getByRole('button', { name: /新增條件/ })).toBeInTheDocument();
  });

  it('emits a default condition when "新增條件" is clicked', () => {
    const calls: unknown[] = [];
    render(
      <ConditionBuilder
        schema={SCHEMA}
        value={[]}
        onChange={(v) => calls.push(v)}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /新增條件/ }));
    expect(calls).toHaveLength(1);
    const newList = calls[0] as Array<{ left: unknown; op: string; right: unknown }>;
    expect(newList.length).toBe(1);
    expect(newList[0].op).toBe('gt');
  });

  it('removes a row when its delete button is clicked', () => {
    const initial = [
      {
        left: { field: 'close' as const },
        op: 'gt' as const,
        right: { const: 100 },
      },
    ];
    const calls: unknown[][] = [];
    render(
      <ConditionBuilder
        schema={SCHEMA}
        value={initial}
        onChange={(v) => calls.push(v)}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /刪除條件/ }));
    expect(calls[0]).toHaveLength(0);
  });

  it('hides entry_price from the var dropdown when allowEntryPrice is false', () => {
    render(
      <ConditionBuilder
        schema={SCHEMA}
        value={[
          {
            left: { field: 'close' as const },
            op: 'gt' as const,
            right: { const: 100 },
          },
        ]}
        onChange={() => {}}
        allowEntryPrice={false}
      />,
    );
    const buttons = screen.queryAllByRole('option', { name: /進場價/ });
    expect(buttons).toHaveLength(0);
  });
});
