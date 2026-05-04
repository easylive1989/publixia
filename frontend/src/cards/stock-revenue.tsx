import { useMemo } from 'react';
import {
  Bar, CartesianGrid, ComposedChart, Legend, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useRevenue, type RevenueRow } from '@/hooks/useRevenue';
import { registerCard } from './registry';

interface ChartRow extends RevenueRow {
  period: string;
}

function RevenueCard() {
  const { data } = useRevenue();
  const rows = useMemo<ChartRow[]>(
    () =>
      (data?.rows ?? []).map((r) => ({
        ...r,
        period: `${r.year}-${String(r.month).padStart(2, '0')}`,
      })),
    [data],
  );
  if (!data) return null;
  if (!rows.length) {
    return (
      <Card>
        <CardHeader><CardTitle>月營收</CardTitle></CardHeader>
        <CardContent><p className="text-sm text-muted-foreground">尚無資料</p></CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>月營收</CardTitle>
        <p className="text-xs text-muted-foreground mt-1">近 36 個月</p>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" hide />
            <YAxis yAxisId="rev" />
            <YAxis yAxisId="yoy" orientation="right" unit="%" />
            <Tooltip formatter={(v: any) => (typeof v === 'number' ? v.toLocaleString() : v)} />
            <Legend />
            <Bar yAxisId="rev" dataKey="revenue" name="月營收" fill="#3b82f6" />
            <Line yAxisId="yoy" dataKey="yoy_pct" name="YoY %" stroke="#dc2626" dot={false} />
            <Line yAxisId="rev" dataKey="ma12" name="12MA" stroke="#a1a1aa" dot={false} strokeDasharray="3 3" />
          </ComposedChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'stock-revenue',
  label: '月營收',
  defaultPage: 'stock',
  component: RevenueCard,
  cols: 3,
});
