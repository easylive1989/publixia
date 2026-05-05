import { useMemo, useState } from 'react';
import {
  Bar, CartesianGrid, Cell, ComposedChart, Legend, Line, LineChart,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import type { ChartRow } from '@/lib/flatten-history';
import { cn } from '@/lib/utils';

const CHART_HEIGHT = 320;

export function ChartCard({ title, hint, action, children }: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>{title}</CardTitle>
          {hint && <p className="text-xs text-muted-foreground mt-1">{hint}</p>}
        </div>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export type Interval = 'day' | 'week' | 'month';

function weekStartKey(date: string): string {
  const d = new Date(date + 'T00:00:00Z');
  const day = d.getUTCDay();
  const offset = day === 0 ? 6 : day - 1;
  d.setUTCDate(d.getUTCDate() - offset);
  return d.toISOString().slice(0, 10);
}

function bucketKey(date: string, interval: Interval): string {
  if (interval === 'week') return weekStartKey(date);
  if (interval === 'month') return date.slice(0, 7);
  return date;
}

export function aggregate(rows: ChartRow[], interval: Interval): ChartRow[] {
  if (interval === 'day') return rows;
  const groups = new Map<string, ChartRow[]>();
  for (const r of rows) {
    const key = bucketKey(r.date, interval);
    const arr = groups.get(key);
    if (arr) arr.push(r);
    else groups.set(key, [r]);
  }
  return Array.from(groups.entries()).map(([key, group]) => {
    const first = group[0];
    const last = group[group.length - 1];
    return {
      date: key,
      open: first.open,
      close: last.close,
      high: Math.max(...group.map((g) => g.high)),
      low: Math.min(...group.map((g) => g.low)),
      volume: group.reduce((s, g) => s + g.volume, 0),
      ma5: null, ma20: null, ma60: null,
      rsi14: null,
      macd: null, macd_signal: null, macd_histogram: null,
      change_pct: null,
    };
  });
}

function CandleShape(props: any) {
  const { x, y, width, height, payload } = props;
  if (!payload) return <g />;
  const { open, high, low, close } = payload;
  if (typeof open !== 'number' || typeof high !== 'number' || typeof low !== 'number' || typeof close !== 'number') return <g />;
  const range = high - low;
  if (range <= 0) {
    const cx = x + width / 2;
    const fill = close >= open ? '#16a34a' : '#dc2626';
    return <line x1={cx - width / 3} x2={cx + width / 3} y1={y} y2={y} stroke={fill} strokeWidth={1} />;
  }
  const slope = height / range;
  const yOpen = y + (high - open) * slope;
  const yClose = y + (high - close) * slope;
  const up = close >= open;
  const fill = up ? '#16a34a' : '#dc2626';
  const cx = x + width / 2;
  const bodyTop = Math.min(yOpen, yClose);
  const bodyH = Math.max(1, Math.abs(yOpen - yClose));
  const bodyW = Math.max(2, width * 0.6);
  return (
    <g>
      <line x1={cx} x2={cx} y1={y} y2={y + height} stroke={fill} strokeWidth={1} />
      <rect x={cx - bodyW / 2} y={bodyTop} width={bodyW} height={bodyH} fill={fill} />
    </g>
  );
}

const INTERVAL_LABELS: Record<Interval, string> = {
  day: '日',
  week: '週',
  month: '月',
};

function IntervalToggle({ value, onChange }: { value: Interval; onChange: (v: Interval) => void }) {
  return (
    <div className="flex gap-1">
      {(Object.keys(INTERVAL_LABELS) as Interval[]).map((iv) => (
        <Button
          key={iv}
          size="sm"
          variant={iv === value ? 'default' : 'outline'}
          onClick={() => onChange(iv)}
          className={cn('px-3')}
        >
          {INTERVAL_LABELS[iv]}
        </Button>
      ))}
    </div>
  );
}

export function KLineChart({ rows: dailyRows }: { rows: ChartRow[] }) {
  const [interval, setInterval] = useState<Interval>('day');
  const rows = useMemo(() => aggregate(dailyRows, interval), [dailyRows, interval]);
  if (!dailyRows.length) return null;
  const showMA = interval === 'day';
  return (
    <ChartCard
      title="K 線圖"
      action={<IntervalToggle value={interval} onChange={setInterval} />}
    >
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" hide />
          <YAxis domain={['auto', 'auto']} />
          <Tooltip
            formatter={(v: any) => (typeof v === 'number' ? v.toLocaleString() : v)}
            labelFormatter={(label) => label as string}
          />
          {showMA && <Legend />}
          <Bar
            dataKey={(row: ChartRow) => [row.low, row.high]}
            shape={<CandleShape />}
            isAnimationActive={false}
            legendType="none"
          />
          {showMA && (
            <>
              <Line dataKey="ma5"  stroke="#f97316" dot={false} name="MA5" />
              <Line dataKey="ma20" stroke="#3b82f6" dot={false} name="MA20" />
              <Line dataKey="ma60" stroke="#a855f7" dot={false} name="MA60" />
            </>
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function VolumeChart({ rows }: { rows: ChartRow[] }) {
  if (!rows.length) return null;
  return (
    <ChartCard title="成交量">
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <XAxis dataKey="date" hide />
          <YAxis />
          <Tooltip formatter={(v: any) => (typeof v === 'number' ? v.toLocaleString() : v)} />
          <Bar dataKey="volume">
            {rows.map((r) => (
              <Cell
                key={r.date}
                fill={
                  r.change_pct == null
                    ? '#a1a1aa'
                    : r.change_pct >= 0
                      ? '#16a34a'
                      : '#dc2626'
                }
              />
            ))}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function RSIChart({ rows }: { rows: ChartRow[] }) {
  if (!rows.length) return null;
  return (
    <ChartCard title="RSI(14)">
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" hide />
          <YAxis domain={[0, 100]} ticks={[0, 30, 50, 70, 100]} />
          <Tooltip formatter={(v: any) => (typeof v === 'number' ? v.toFixed(2) : v)} />
          <ReferenceLine y={70} stroke="#fca5a5" strokeDasharray="4 4" />
          <ReferenceLine y={30} stroke="#86efac" strokeDasharray="4 4" />
          <Line dataKey="rsi14" stroke="#3b82f6" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function MACDChart({ rows }: { rows: ChartRow[] }) {
  if (!rows.length) return null;
  return (
    <ChartCard title="MACD(12,26,9)">
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" hide />
          <YAxis />
          <Tooltip formatter={(v: any) => (typeof v === 'number' ? v.toFixed(3) : v)} />
          <ReferenceLine y={0} stroke="#71717a" />
          <Bar dataKey="macd_histogram">
            {rows.map((r) => (
              <Cell
                key={r.date}
                fill={(r.macd_histogram ?? 0) >= 0 ? '#16a34a' : '#dc2626'}
              />
            ))}
          </Bar>
          <Line dataKey="macd"        stroke="#3b82f6" dot={false} />
          <Line dataKey="macd_signal" stroke="#f97316" dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
