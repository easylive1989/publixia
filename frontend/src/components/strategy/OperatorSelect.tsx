import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';

const OP_LABELS: Record<string, string> = {
  gt: '>', gte: '>=', lt: '<', lte: '<=',
  cross_above: '上穿', cross_below: '下穿',
  streak_above: '連 N 日 ≥', streak_below: '連 N 日 ≤',
};

interface Props {
  value: string;
  onChange: (v: string) => void;
  operators: string[];
}

export function OperatorSelect({ value, onChange, operators }: Props) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-32" aria-label="運算子">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {operators.map((op) => (
          <SelectItem key={op} value={op}>
            {OP_LABELS[op] ?? op}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
