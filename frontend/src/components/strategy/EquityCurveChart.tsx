import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import type { BacktestTrade } from '@/hooks/useStrategy';

export function EquityCurveChart({ trades }: { trades: BacktestTrade[] }) {
  if (!trades.length) return null;

  const points: { date: string; cumulative: number }[] = [];
  let cumulative = 0;
  for (const t of trades) {
    cumulative += t.pnl_amount;
    points.push({ date: t.exit_date, cumulative });
  }

  return (
    <div style={{ width: '100%', height: 240 }}>
      <ResponsiveContainer>
        <LineChart data={points} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis
            tick={{ fontSize: 11 }}
            tickFormatter={(v) => v.toLocaleString()}
          />
          <Tooltip
            formatter={(v) =>
              typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
            }
            labelFormatter={(d) => `出場日:${d}`}
          />
          <Line
            type="monotone"
            dataKey="cumulative"
            name="累計 PnL"
            stroke="#10b981"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
