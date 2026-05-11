import { useMemo } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ForeignFuturesResponse } from '@/hooks/useForeignFutures';
import { POSITIVE, NEGATIVE, SYNC_ID } from './colors';

interface SpotRow {
  date: string;
  value: number | null;
}

const BILLIONS_FMT = (v: number | null | undefined) =>
  v == null ? '—'
    : `${v > 0 ? '+' : ''}${v.toFixed(2)} 億`;

function SpotTooltip({ active, label, payload }: any) {
  if (!active || !payload?.length) return null;
  const row: SpotRow | undefined = payload[0]?.payload;
  if (!row) return null;
  const v = row.value;
  return (
    <div className="rounded-md border bg-background/95 px-3 py-2 text-xs shadow-md">
      <div className="font-medium mb-1">{label}</div>
      <div className={`font-mono tabular-nums ${
        v == null ? '' : v >= 0 ? 'text-green-600' : 'text-red-600'
      }`}>
        外資現貨淨買賣超 {BILLIONS_FMT(v)}
      </div>
    </div>
  );
}

export function ForeignSpotChart({ data }: { data: ForeignFuturesResponse }) {
  const rows: SpotRow[] = useMemo(
    () => data.dates.map((d, i) => ({ date: d, value: data.foreign_spot_net[i] ?? null })),
    [data.dates, data.foreign_spot_net],
  );

  const hasAny = rows.some((r) => r.value != null);
  const last = [...rows].reverse().find((r) => r.value != null);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-medium">
          外資現貨淨買賣超 (TWSE 整體)
        </CardTitle>
        {last && (
          <p className={`text-xs mt-0.5 font-mono tabular-nums ${
            last.value == null
              ? 'text-muted-foreground'
              : last.value >= 0 ? 'text-green-600' : 'text-red-600'
          }`}>
            {last.date} · {BILLIONS_FMT(last.value)}
          </p>
        )}
      </CardHeader>
      <CardContent className="pt-2">
        {!hasAny ? (
          <p className="text-sm text-muted-foreground">此期間無外資現貨資料。</p>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={rows} syncId={SYNC_ID}
              margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" hide />
              <YAxis width={60}
                tickFormatter={(v: number) => `${v.toFixed(0)} 億`} />
              <Tooltip content={<SpotTooltip />} cursor={{ fill: 'rgba(148,163,184,0.1)' }} />
              <ReferenceLine y={0} stroke="#94a3b8" />
              {data.settlement_dates.map((d) => (
                <ReferenceLine
                  key={d}
                  x={d}
                  stroke="#94a3b8"
                  strokeDasharray="2 4"
                />
              ))}
              <Bar dataKey="value" name="外資現貨淨買賣超" isAnimationActive={false}>
                {rows.map((r, i) => (
                  <Cell key={i}
                    fill={r.value == null
                      ? '#cbd5e1'
                      : r.value >= 0 ? POSITIVE : NEGATIVE} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
