import { useMemo } from 'react';
import {
  CartesianGrid, ComposedChart, Legend, Line,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ForeignFuturesResponse } from '@/hooks/useForeignFutures';
import { POSITIVE, NEGATIVE, SYNC_ID } from './colors';

interface ChartRow {
  date: string;
  long_amount: number | null;
  short_amount: number | null;
}

// 千元 → 億元
const toBillions = (v: number | null) =>
  v == null ? null : v / 100_000;

const BILLIONS_FMT = (v: number | null) =>
  v == null ? '—' : `${v.toFixed(2)} 億`;

function OptionsTooltip({ active, label, payload }: any) {
  if (!active || !payload?.length) return null;
  const row: ChartRow | undefined = payload[0]?.payload;
  if (!row) return null;
  const net = row.long_amount != null && row.short_amount != null
    ? row.long_amount - row.short_amount
    : null;
  return (
    <div className="rounded-md border bg-background/95 px-3 py-2 text-xs shadow-md">
      <div className="font-medium mb-1">{label}</div>
      <table className="border-separate [border-spacing:0_2px]">
        <tbody>
          <tr>
            <td className="pr-3 text-muted-foreground">
              <span
                className="inline-block w-2 h-2 rounded-sm align-middle mr-1"
                style={{ background: POSITIVE }}
              />
              多方契約金額
            </td>
            <td className="text-right font-mono tabular-nums">
              {BILLIONS_FMT(row.long_amount)}
            </td>
          </tr>
          <tr>
            <td className="pr-3 text-muted-foreground">
              <span
                className="inline-block w-2 h-2 rounded-sm align-middle mr-1"
                style={{ background: NEGATIVE }}
              />
              空方契約金額
            </td>
            <td className="text-right font-mono tabular-nums">
              {BILLIONS_FMT(row.short_amount)}
            </td>
          </tr>
          <tr>
            <td className="pr-3 text-muted-foreground">多空淨額</td>
            <td className={`text-right font-mono tabular-nums ${
              net == null ? '' : net >= 0 ? 'text-green-600' : 'text-red-600'
            }`}>
              {BILLIONS_FMT(net)}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

interface SingleChartProps {
  title: string;
  subtitle: string | undefined;
  rows: ChartRow[];
  settlementDates: string[];
}

function SingleChart({ title, subtitle, rows, settlementDates }: SingleChartProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-medium">{title}</CardTitle>
        {subtitle && (
          <p className="text-xs text-muted-foreground mt-0.5 font-mono tabular-nums">
            {subtitle}
          </p>
        )}
      </CardHeader>
      <CardContent className="pt-2">
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={rows} syncId={SYNC_ID}
            margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" hide />
            <YAxis width={60}
              tickFormatter={(v: number) => `${v.toFixed(0)} 億`} />
            <Tooltip content={<OptionsTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine y={0} stroke="#94a3b8" />
            {settlementDates.map((d) => (
              <ReferenceLine
                key={d}
                x={d}
                stroke="#94a3b8"
                strokeDasharray="2 4"
              />
            ))}
            <Line dataKey="long_amount" stroke={POSITIVE} dot={false}
              strokeWidth={1.5} name="多方契約金額" connectNulls />
            <Line dataKey="short_amount" stroke={NEGATIVE} dot={false}
              strokeWidth={1.5} name="空方契約金額" connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export function ForeignOptionsAmountChart({ data }: { data: ForeignFuturesResponse }) {
  const opt = data.options;

  const callRows: ChartRow[] = useMemo(() => {
    if (!opt) return [];
    return data.dates.map((d, i) => ({
      date: d,
      long_amount:  toBillions(opt.foreign_call_long_amount[i]  ?? null),
      short_amount: toBillions(opt.foreign_call_short_amount[i] ?? null),
    }));
  }, [data.dates, opt]);

  const putRows: ChartRow[] = useMemo(() => {
    if (!opt) return [];
    return data.dates.map((d, i) => ({
      date: d,
      long_amount:  toBillions(opt.foreign_put_long_amount[i]  ?? null),
      short_amount: toBillions(opt.foreign_put_short_amount[i] ?? null),
    }));
  }, [data.dates, opt]);

  if (!opt) return null;

  const callLast = callRows[callRows.length - 1];
  const putLast = putRows[putRows.length - 1];

  const callSubtitle = callLast
    ? `多方 ${BILLIONS_FMT(callLast.long_amount)} · 空方 ${BILLIONS_FMT(callLast.short_amount)}`
    : undefined;
  const putSubtitle = putLast
    ? `多方 ${BILLIONS_FMT(putLast.long_amount)} · 空方 ${BILLIONS_FMT(putLast.short_amount)}`
    : undefined;

  return (
    <div className="space-y-3">
      <SingleChart
        title="外資 TXO 買權 多空未平倉契約金額"
        subtitle={callSubtitle}
        rows={callRows}
        settlementDates={data.settlement_dates}
      />
      <SingleChart
        title="外資 TXO 賣權 多空未平倉契約金額"
        subtitle={putSubtitle}
        rows={putRows}
        settlementDates={data.settlement_dates}
      />
    </div>
  );
}
