import { useMemo } from 'react';
import {
  CartesianGrid, ComposedChart, Legend, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useChip } from '@/hooks/useChip';
import { registerCard } from './registry';

function ChipCard() {
  const { data } = useChip();
  const rows = useMemo(() => data?.rows ?? [], [data]);
  if (!data) return null;
  if (rows.length === 0) {
    return (
      <Card>
        <CardHeader><CardTitle>籌碼面</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">尚無資料</p>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>籌碼面</CardTitle>
        <p className="text-xs text-muted-foreground mt-1">近 20 個交易日</p>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" hide />
            <YAxis yAxisId="net" />
            <YAxis yAxisId="margin" orientation="right" />
            <Tooltip formatter={(v: any) => (typeof v === 'number' ? v.toLocaleString() : v)} />
            <Legend />
            <ReferenceLine y={0} yAxisId="net" stroke="#71717a" />
            <Line yAxisId="net" dataKey="foreign_net" name="外資" stroke="#3b82f6" dot={false} />
            <Line yAxisId="net" dataKey="trust_net"   name="投信" stroke="#16a34a" dot={false} />
            <Line yAxisId="net" dataKey="dealer_net"  name="自營" stroke="#f97316" dot={false} />
            <Line yAxisId="margin" dataKey="margin_balance" name="融資" stroke="#a855f7" dot={false} strokeDasharray="3 3" />
            <Line yAxisId="margin" dataKey="short_balance"  name="融券" stroke="#dc2626" dot={false} strokeDasharray="3 3" />
          </ComposedChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'stock-chip',
  label: '籌碼面',
  defaultPage: 'stock',
  component: ChipCard,
  cols: 3,
});
