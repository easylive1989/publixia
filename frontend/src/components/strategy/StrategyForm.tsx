import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { ConditionBuilder } from './ConditionBuilder';
import { ExitConditionEditor, type ExitDsl } from './ExitConditionEditor';
import type { DslCondition } from './ConditionRow';
import type {
  DslSchema, StrategyCreatePayload, StrategyUpdatePayload, Strategy,
} from '@/hooks/useStrategy';

interface Initial {
  name: string;
  direction: 'long' | 'short';
  contract: 'TX' | 'MTX' | 'TMF';
  contract_size: number;
  max_hold_days: number | null;
  entry_dsl: { version: 1; all: DslCondition[] };
  take_profit_dsl: ExitDsl;
  stop_loss_dsl: ExitDsl;
  state?: Strategy['state'];
}

interface Props {
  schema: DslSchema;
  mode: 'create' | 'edit';
  initial?: Initial;
  onSubmit: (payload: StrategyCreatePayload | StrategyUpdatePayload) => void;
  saving?: boolean;
  serverError?: string | null;
}

const DEFAULT: Initial = {
  name: '',
  direction: 'long',
  contract: 'TX',
  contract_size: 1,
  max_hold_days: null,
  entry_dsl:       { version: 1, all: [] },
  take_profit_dsl: { version: 1, type: 'pct', value: 2.0 },
  stop_loss_dsl:   { version: 1, type: 'pct', value: 1.0 },
};

export function StrategyForm({
  schema, mode, initial, onSubmit, saving, serverError,
}: Props) {
  const [state, setState] = useState<Initial>(initial ?? DEFAULT);
  const [validationError, setValidationError] = useState<string | null>(null);
  const inPosition = mode === 'edit' && state.state !== undefined && state.state !== 'idle';

  const handleSubmit = () => {
    if (!state.name.trim()) {
      setValidationError('請輸入名稱');
      return;
    }
    if (state.entry_dsl.all.length === 0) {
      setValidationError('進場條件至少需要一條規則');
      return;
    }
    setValidationError(null);
    onSubmit({
      name: state.name.trim(),
      direction: state.direction,
      contract: state.contract,
      contract_size: state.contract_size,
      max_hold_days: state.max_hold_days,
      entry_dsl: state.entry_dsl,
      take_profit_dsl: state.take_profit_dsl,
      stop_loss_dsl: state.stop_loss_dsl,
    });
  };

  return (
    <div className="space-y-4">
      {inPosition && (
        <div className="text-sm text-amber-700 bg-amber-500/10 p-2 rounded">
          策略目前在場內,條件已凍結。如需調整條件請先「重置」或「強制平倉」。
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <label htmlFor="strat-name" className="text-sm">名稱</label>
          <Input
            id="strat-name"
            aria-label="名稱"
            value={state.name}
            onChange={(e) => setState({ ...state, name: e.target.value })}
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="strat-direction" className="text-sm">方向</label>
          <Select
            value={state.direction}
            onValueChange={(v) =>
              setState({ ...state, direction: v as 'long' | 'short' })
            }
            disabled={inPosition}
          >
            <SelectTrigger id="strat-direction" aria-label="方向">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="long">多 (long)</SelectItem>
              <SelectItem value="short">空 (short)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <label htmlFor="strat-contract" className="text-sm">商品</label>
          <Select
            value={state.contract}
            onValueChange={(v) =>
              setState({ ...state, contract: v as 'TX' | 'MTX' | 'TMF' })
            }
            disabled={inPosition}
          >
            <SelectTrigger id="strat-contract" aria-label="商品">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="TX">大台 (TX)</SelectItem>
              <SelectItem value="MTX">小台 (MTX)</SelectItem>
              <SelectItem value="TMF">微台 (TMF)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <label htmlFor="strat-size" className="text-sm">口數</label>
          <Input
            id="strat-size"
            aria-label="口數"
            type="number"
            min={1}
            value={state.contract_size}
            onChange={(e) =>
              setState({ ...state, contract_size: Math.max(1, Number(e.target.value)) })
            }
          />
        </div>

        <div className="space-y-1 sm:col-span-2">
          <label htmlFor="strat-max-hold" className="text-sm">
            最大持倉天數 (留空 = 不限)
          </label>
          <Input
            id="strat-max-hold"
            type="number"
            min={1}
            value={state.max_hold_days ?? ''}
            disabled={inPosition}
            onChange={(e) =>
              setState({
                ...state,
                max_hold_days: e.target.value ? Number(e.target.value) : null,
              })
            }
          />
        </div>
      </div>

      <fieldset disabled={inPosition} className="space-y-2">
        <legend className="text-sm font-medium">進場條件 (AND)</legend>
        <ConditionBuilder
          schema={schema}
          value={state.entry_dsl.all}
          onChange={(all) => setState({ ...state, entry_dsl: { version: 1, all } })}
          allowEntryPrice={false}
        />
      </fieldset>

      <fieldset disabled={inPosition} className="space-y-2">
        <legend className="text-sm font-medium">停利</legend>
        <ExitConditionEditor
          schema={schema}
          value={state.take_profit_dsl}
          onChange={(take_profit_dsl) => setState({ ...state, take_profit_dsl })}
        />
      </fieldset>

      <fieldset disabled={inPosition} className="space-y-2">
        <legend className="text-sm font-medium">停損</legend>
        <ExitConditionEditor
          schema={schema}
          value={state.stop_loss_dsl}
          onChange={(stop_loss_dsl) => setState({ ...state, stop_loss_dsl })}
        />
      </fieldset>

      {(validationError || serverError) && (
        <div className="text-destructive text-sm">
          {validationError ?? serverError}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button
          type="button"
          onClick={handleSubmit}
          disabled={saving}
        >
          {saving ? '儲存中…' : '儲存'}
        </Button>
      </div>
    </div>
  );
}
