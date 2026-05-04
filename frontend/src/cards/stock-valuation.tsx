import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useValuation, type ValuationRange } from '@/hooks/useValuation';
import { cn } from '@/lib/utils';
import { registerCard } from './registry';

function fmt(n: number | null | undefined, digits = 2): string {
  return n == null ? '—' : n.toFixed(digits);
}

interface StatProps {
  label: string;
  value: number | null;
  percentile?: number | null;
  range?: ValuationRange | null;
  suffix?: string;
}

function Stat({ label, value, percentile, range, suffix = '' }: StatProps) {
  const pBadge = percentile == null ? null : (
    <span
      className={cn(
        'text-xs px-2 py-0.5 rounded',
        percentile <= 30
          ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200'
          : percentile >= 70
            ? 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200'
            : 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200',
      )}
    >
      5y 百分位 {percentile.toFixed(0)}%
    </span>
  );
  const rangeText =
    range && range.min != null && range.max != null
      ? `5y ${fmt(range.min)} – ${fmt(range.max)}（均 ${fmt(range.avg)}）`
      : null;
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-2xl font-bold">{fmt(value)}{suffix}</span>
      {pBadge}
      {rangeText && (
        <span className="text-xs text-muted-foreground">{rangeText}</span>
      )}
    </div>
  );
}

function ValuationCard() {
  const { data } = useValuation();
  if (!data) return null;
  const { latest, range_5y, rows } = data;
  if (!rows || !rows.length) {
    return (
      <Card>
        <CardHeader><CardTitle>估值快照</CardTitle></CardHeader>
        <CardContent><p className="text-sm text-muted-foreground">尚無資料</p></CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>估值快照</CardTitle>
        <p className="text-xs text-muted-foreground mt-1">PER / PBR / 殖利率 · 近 5 年</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-4">
          <Stat
            label="PER"
            value={latest.per}
            percentile={latest.per_percentile_5y}
            range={range_5y?.per}
          />
          <Stat label="PBR" value={latest.pbr} range={range_5y?.pbr} />
          <Stat
            label="殖利率"
            value={latest.dividend_yield}
            range={range_5y?.dividend_yield}
            suffix="%"
          />
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" hide />
            <YAxis />
            <Tooltip formatter={(v: any) => (typeof v === 'number' ? v.toFixed(2) : v)} />
            <Line dataKey="per" stroke="#3b82f6" dot={false} name="PER" />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'stock-valuation',
  label: '估值快照',
  defaultPage: 'stock',
  component: ValuationCard,
  cols: 3,
});
