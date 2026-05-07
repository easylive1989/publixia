import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ConditionBuilder } from './ConditionBuilder';
import type { DslCondition } from './ConditionRow';
import type { DslSchema } from '@/hooks/useStrategy';

export type ExitDsl =
  | { version: 1; type: 'pct';    value: number }
  | { version: 1; type: 'points'; value: number }
  | { version: 1; type: 'dsl';    all:   DslCondition[] };

type Mode = ExitDsl['type'];

interface Props {
  value: ExitDsl;
  onChange: (v: ExitDsl) => void;
  schema: DslSchema;
}

export function ExitConditionEditor({ value, onChange, schema }: Props) {
  const [mode, setModeState] = useState<Mode>(value.type);

  // derive displayed content from local mode + prop value
  const activeType = mode;

  function setMode(m: Mode) {
    setModeState(m);
    if (m === 'pct')         onChange({ version: 1, type: 'pct',    value: 2.0 });
    else if (m === 'points') onChange({ version: 1, type: 'points', value: 50  });
    else                     onChange({ version: 1, type: 'dsl',    all:   []  });
  }

  // For the body we use 'value' from props when types match, otherwise defaults
  const pctValue   = value.type === 'pct'    ? value.value : 2.0;
  const pointValue = value.type === 'points' ? value.value : 50;
  const dslAll     = value.type === 'dsl'    ? value.all   : [];

  return (
    <div className="space-y-2">
      <div className="flex gap-1" aria-label="出場模式">
        <Button
          type="button" size="sm"
          variant={activeType === 'pct'    ? 'default' : 'outline'}
          aria-pressed={activeType === 'pct'}
          onClick={() => setMode('pct')}
        >百分比</Button>
        <Button
          type="button" size="sm"
          variant={activeType === 'points' ? 'default' : 'outline'}
          aria-pressed={activeType === 'points'}
          onClick={() => setMode('points')}
        >點數</Button>
        <Button
          type="button" size="sm"
          variant={activeType === 'dsl'    ? 'default' : 'outline'}
          aria-pressed={activeType === 'dsl'}
          onClick={() => setMode('dsl')}
        >進階</Button>
      </div>

      {activeType === 'pct' && (
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground" htmlFor="exit-pct">
            百分比 (%)
          </label>
          <Input
            id="exit-pct"
            type="number"
            step="0.1"
            min={0}
            className="w-24"
            value={pctValue}
            onChange={(e) =>
              onChange({ version: 1, type: 'pct', value: Number(e.target.value) })
            }
          />
        </div>
      )}

      {activeType === 'points' && (
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground" htmlFor="exit-points">
            點數
          </label>
          <Input
            id="exit-points"
            type="number"
            step="1"
            min={0}
            className="w-24"
            value={pointValue}
            onChange={(e) =>
              onChange({ version: 1, type: 'points', value: Number(e.target.value) })
            }
          />
        </div>
      )}

      {activeType === 'dsl' && (
        <ConditionBuilder
          value={dslAll}
          onChange={(all) => onChange({ version: 1, type: 'dsl', all })}
          schema={schema}
          allowEntryPrice={true}
        />
      )}
    </div>
  );
}
