import { useMemo } from 'react';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import type { DslSchema } from '@/hooks/useStrategy';

export type Expression =
  | { field: string }
  | { indicator: string; [key: string]: unknown }
  | { const: number }
  | { var: 'entry_price' };

type Kind = 'field' | 'indicator' | 'const' | 'var';

function kindOf(expr: Expression): Kind {
  if ('field' in expr) return 'field';
  if ('indicator' in expr) return 'indicator';
  if ('const' in expr) return 'const';
  return 'var';
}

interface Props {
  value: Expression;
  onChange: (v: Expression) => void;
  schema: DslSchema;
  allowEntryPrice: boolean;
}

const KIND_LABELS: Record<Kind, string> = {
  field:     '欄位',
  indicator: '指標',
  const:     '常數',
  var:       '進場價',
};

export function ExpressionPicker({ value, onChange, schema, allowEntryPrice }: Props) {
  const currentKind = kindOf(value);

  const kinds = useMemo<Kind[]>(() => {
    const out: Kind[] = ['field', 'indicator', 'const'];
    if (allowEntryPrice) out.push('var');
    return out;
  }, [allowEntryPrice]);

  function changeKind(k: Kind) {
    if (k === 'field')     onChange({ field: schema.fields[0] ?? 'close' });
    else if (k === 'indicator') {
      const ind = schema.indicators[0];
      const params: Record<string, unknown> = { indicator: ind.name };
      ind.params.forEach((p) => {
        params[p.name] =
          p.default !== undefined ? p.default :
          p.type === 'enum' ? p.choices?.[0] ?? '' :
          p.type === 'int' ? (p.min ?? 1) :
          (p.min ?? 1);
      });
      onChange(params as Expression);
    }
    else if (k === 'const') onChange({ const: 0 });
    else                    onChange({ var: 'entry_price' });
  }

  return (
    <div className="flex items-center gap-2">
      <Select value={currentKind} onValueChange={(v) => changeKind(v as Kind)}>
        <SelectTrigger className="w-24" aria-label="表達式種類">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {kinds.map((k) => (
            <SelectItem
              key={k}
              value={k}
              role="option"
              aria-label={KIND_LABELS[k]}
            >
              {KIND_LABELS[k]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {currentKind === 'field' && (
        <Select
          value={(value as { field: string }).field}
          onValueChange={(f) => onChange({ field: f })}
        >
          <SelectTrigger className="w-24" aria-label="欄位">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {schema.fields.map((f) => (
              <SelectItem key={f} value={f}>{f}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {currentKind === 'indicator' && (
        <IndicatorParamsRow
          value={value as { indicator: string; [k: string]: unknown }}
          onChange={onChange}
          schema={schema}
        />
      )}

      {currentKind === 'const' && (
        <Input
          type="number"
          step="any"
          className="w-32"
          aria-label="常數"
          value={(value as { const: number }).const}
          onChange={(e) => onChange({ const: Number(e.target.value) })}
        />
      )}

      {currentKind === 'var' && (
        <span className="text-sm text-muted-foreground">entry_price</span>
      )}
    </div>
  );
}

function IndicatorParamsRow({
  value, onChange, schema,
}: {
  value: { indicator: string; [k: string]: unknown };
  onChange: (v: Expression) => void;
  schema: DslSchema;
}) {
  const ind = schema.indicators.find((i) => i.name === value.indicator);
  if (!ind) return null;

  return (
    <div className="flex items-center gap-1">
      <Select
        value={value.indicator}
        onValueChange={(name) => {
          const next = schema.indicators.find((i) => i.name === name);
          if (!next) return;
          const out: Record<string, unknown> = { indicator: name };
          next.params.forEach((p) => {
            out[p.name] =
              p.default !== undefined ? p.default :
              p.type === 'enum' ? p.choices?.[0] ?? '' :
              p.type === 'int' ? (p.min ?? 1) :
              (p.min ?? 1);
          });
          onChange(out as Expression);
        }}
      >
        <SelectTrigger className="w-32" aria-label="指標">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {schema.indicators.map((i) => (
            <SelectItem key={i.name} value={i.name}>{i.name}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {ind.params.map((p) =>
        p.type === 'enum' ? (
          <Select
            key={p.name}
            value={String(value[p.name])}
            onValueChange={(v) => onChange({ ...value, [p.name]: v } as Expression)}
          >
            <SelectTrigger className="w-24" aria-label={p.name}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(p.choices ?? []).map((c) => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Input
            key={p.name}
            type="number"
            className="w-20"
            aria-label={p.name}
            value={Number(value[p.name] ?? 0)}
            onChange={(e) =>
              onChange({ ...value, [p.name]: Number(e.target.value) } as Expression)
            }
          />
        ),
      )}
    </div>
  );
}
