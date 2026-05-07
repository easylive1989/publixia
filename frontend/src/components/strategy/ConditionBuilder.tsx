import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';
import { ConditionRow, type DslCondition } from './ConditionRow';
import type { DslSchema } from '@/hooks/useStrategy';

interface Props {
  value: DslCondition[];
  onChange: (v: DslCondition[]) => void;
  schema: DslSchema;
  /** True only inside the take_profit / stop_loss "advanced" editor;
   *  entry conditions cannot reference {var: entry_price}. */
  allowEntryPrice?: boolean;
  maxConditions?: number;
}

export function ConditionBuilder({
  value, onChange, schema,
  allowEntryPrice = false, maxConditions = 5,
}: Props) {
  const addCondition = () => {
    const initial: DslCondition = {
      left:  { field: schema.fields[0] ?? 'close' },
      op:    schema.operators[0] ?? 'gt',
      right: { const: 0 },
    };
    onChange([...value, initial]);
  };

  return (
    <div className="space-y-1">
      {value.map((c, i) => (
        <ConditionRow
          key={i}
          value={c}
          onChange={(updated) => {
            const copy = [...value];
            copy[i] = updated;
            onChange(copy);
          }}
          onDelete={() => onChange(value.filter((_, idx) => idx !== i))}
          schema={schema}
          allowEntryPrice={allowEntryPrice}
        />
      ))}
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={addCondition}
        disabled={value.length >= maxConditions}
      >
        <Plus className="h-4 w-4 mr-1" />
        新增條件
      </Button>
      {value.length >= maxConditions && (
        <p className="text-xs text-muted-foreground">
          已達 {maxConditions} 條上限。再多通常代表過度擬合。
        </p>
      )}
    </div>
  );
}
