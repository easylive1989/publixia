import {
  Bar, CartesianGrid, ComposedChart, Legend, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useDividend } from '@/hooks/useDividend';
import { registerCard } from './registry';

function DividendCard() {
  const { data } = useDividend();
  if (!data) return null;
  if (!data.rows.length) {
    return (
      <Card>
        <CardHeader><CardTitle>股利歷史</CardTitle></CardHeader>
        <CardContent><p className="text-sm text-muted-foreground">尚無資料</p></CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>股利歷史</CardTitle>
        <p className="text-xs text-muted-foreground mt-1">近 10 年</p>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={data.rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="year" />
            <YAxis yAxisId="div" />
            <YAxis yAxisId="payout" orientation="right" unit="%" />
            <Tooltip formatter={(v: any) => (typeof v === 'number' ? v.toFixed(2) : v)} />
            <Legend />
            <Bar yAxisId="div" dataKey="cash_dividend"  name="現金股利" stackId="d" fill="#16a34a" />
            <Bar yAxisId="div" dataKey="stock_dividend" name="股票股利" stackId="d" fill="#3b82f6" />
            <Line yAxisId="payout" dataKey="payout_ratio_pct" name="配發率" stroke="#dc2626" dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'stock-dividend',
  label: '股利歷史',
  defaultPage: 'stock',
  component: DividendCard,
  cols: 3,
});
