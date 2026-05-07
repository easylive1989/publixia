import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Trash2 } from 'lucide-react';
import { ExpressionPicker, type Expression } from './ExpressionPicker';
import { OperatorSelect } from './OperatorSelect';
import type { DslSchema } from '@/hooks/useStrategy';

export interface DslCondition {
  left:  Expression;
  op:    string;
  right: Expression;
  n?:    number;
}

interface Props {
  value: DslCondition;
  onChange: (v: DslCondition) => void;
  onDelete: () => void;
  schema: DslSchema;
  allowEntryPrice: boolean;
}

export function ConditionRow({
  value, onChange, onDelete, schema, allowEntryPrice,
}: Props) {
  const isStreak =
    value.op === 'streak_above' || value.op === 'streak_below';

  return (
    <div className="flex flex-wrap items-center gap-2 py-1">
      <ExpressionPicker
        value={value.left}
        onChange={(left) => onChange({ ...value, left })}
        schema={schema}
        allowEntryPrice={allowEntryPrice}
      />
      <OperatorSelect
        value={value.op}
        onChange={(op) => {
          const next: DslCondition = { ...value, op };
          if (op === 'streak_above' || op === 'streak_below') {
            next.n = next.n ?? 3;
          } else {
            delete next.n;
          }
          onChange(next);
        }}
        operators={schema.operators}
      />
      {isStreak && (
        <Input
          type="number"
          min={1}
          className="w-16"
          aria-label="n"
          value={value.n ?? 3}
          onChange={(e) =>
            onChange({ ...value, n: Math.max(1, Number(e.target.value)) })
          }
        />
      )}
      <ExpressionPicker
        value={value.right}
        onChange={(right) => onChange({ ...value, right })}
        schema={schema}
        allowEntryPrice={allowEntryPrice}
      />
      <Button
        type="button"
        size="icon"
        variant="ghost"
        aria-label="刪除條件"
        onClick={onDelete}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}
