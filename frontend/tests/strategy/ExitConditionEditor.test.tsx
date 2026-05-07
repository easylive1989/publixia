import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ExitConditionEditor } from '../../src/components/strategy/ExitConditionEditor';
import type { DslSchema } from '../../src/hooks/useStrategy';

const SCHEMA: DslSchema = {
  version: 1,
  fields: ['close'],
  operators: ['gt', 'lt'],
  indicators: [],
  exit_modes: ['pct', 'points', 'dsl'],
  vars: ['entry_price'],
};

describe('ExitConditionEditor', () => {
  it('starts in pct mode and emits {type:pct,value} on change', () => {
    const calls: unknown[] = [];
    render(
      <ExitConditionEditor
        schema={SCHEMA}
        value={{ version: 1, type: 'pct', value: 2.0 }}
        onChange={(v) => calls.push(v)}
      />,
    );
    const input = screen.getByLabelText(/百分比/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '3.5' } });
    expect(calls.at(-1)).toMatchObject({ type: 'pct', value: 3.5 });
  });

  it('switches to points mode and resets value', () => {
    const calls: unknown[] = [];
    render(
      <ExitConditionEditor
        schema={SCHEMA}
        value={{ version: 1, type: 'pct', value: 2.0 }}
        onChange={(v) => calls.push(v)}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /^點數$/ }));
    expect(calls.at(-1)).toMatchObject({ type: 'points' });
  });

  it('switches to advanced (dsl) mode and shows the ConditionBuilder', () => {
    render(
      <ExitConditionEditor
        schema={SCHEMA}
        value={{ version: 1, type: 'pct', value: 2.0 }}
        onChange={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /進階/ }));
    expect(screen.getByRole('button', { name: /新增條件/ })).toBeInTheDocument();
  });
});
