import { useMemo } from 'react';
import {
  Bar, CartesianGrid, Cell, ComposedChart, Line,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ForeignFuturesResponse } from '@/hooks/useForeignFutures';

const SYNC_ID = 'foreign-futures-flow';
const POSITIVE = '#16a34a';
const NEGATIVE = '#dc2626';
const COST_LINE = '#3b82f6';
const NET_LINE = '#f59e0b';
const RETAIL_LINE = '#a855f7';

interface Row {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  cost: number | null;
  net_position: number | null;
  net_change: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number;
  retail_ratio: number | null;
}

// Shared CandleShape — same idea as PriceCharts.tsx but inlined to keep
// each chart module self-contained.
function CandleShape(props: any) {
  const { x, y, width, height, payload } = props;
  if (!payload) return <g />;
  const { open, high, low, close } = payload;
  if (
    typeof open !== 'number' || typeof high !== 'number' ||
    typeof low !== 'number'  || typeof close !== 'number'
  ) return <g />;
  const range = high - low;
  if (range <= 0) {
    const cx = x + width / 2;
    const fill = close >= open ? POSITIVE : NEGATIVE;
    return <line x1={cx - width / 3} x2={cx + width / 3}
      y1={y} y2={y} stroke={fill} strokeWidth={1} />;
  }
  const slope = height / range;
  const yOpen  = y + (high - open)  * slope;
  const yClose = y + (high - close) * slope;
  const up = close >= open;
  const fill = up ? POSITIVE : NEGATIVE;
  const cx = x + width / 2;
  const bodyTop = Math.min(yOpen, yClose);
  const bodyH = Math.max(1, Math.abs(yOpen - yClose));
  const bodyW = Math.max(2, width * 0.6);
  return (
    <g>
      <line x1={cx} x2={cx} y1={y} y2={y + height}
        stroke={fill} strokeWidth={1} />
      <rect x={cx - bodyW / 2} y={bodyTop}
        width={bodyW} height={bodyH} fill={fill} />
    </g>
  );
}

const LOTS_FMT  = (v: number | null) =>
  v == null ? '—' : Math.round(v).toLocaleString();
const POINTS_FMT = (v: number | null) =>
  v == null ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
/** NT$ → 萬元 (TWD ÷ 10,000), no decimals — matches the reference figure. */
const TENK_FMT = (v: number | null) =>
  v == null ? '—' : Math.round(v / 10_000).toLocaleString();
const PCT_FMT = (v: number | null) =>
  v == null ? '—' : `${v.toFixed(2)}%`;

interface SeriesValue {
  name: string;
  value: number | null;
  formatter: (v: number | null) => string;
  color?: string;
}

function SharedTooltip({ active, label, payload }: any) {
  if (!active || !payload?.length) return null;
  const row: Row | undefined = payload[0]?.payload;
  if (!row) return null;
  const items: SeriesValue[] = [
    { name: '開', value: row.open,  formatter: POINTS_FMT },
    { name: '高', value: row.high,  formatter: POINTS_FMT },
    { name: '低', value: row.low,   formatter: POINTS_FMT },
    { name: '收', value: row.close, formatter: POINTS_FMT },
    { name: '持倉成本',     value: row.cost,           formatter: POINTS_FMT, color: COST_LINE },
    { name: '多空未平倉淨額', value: row.net_position,   formatter: LOTS_FMT,   color: NET_LINE  },
    { name: '日變動',         value: row.net_change,     formatter: LOTS_FMT },
    { name: '未實現損益(萬元)', value: row.unrealized_pnl, formatter: TENK_FMT },
    { name: '已實現損益(萬元)', value: row.realized_pnl,   formatter: TENK_FMT },
    { name: '散戶多空比',       value: row.retail_ratio,   formatter: PCT_FMT, color: RETAIL_LINE },
  ];
  return (
    <div className="rounded-md border bg-background/95 px-3 py-2 text-xs shadow-md">
      <div className="font-medium mb-1">{label}</div>
      <table className="border-separate [border-spacing:0_2px]">
        <tbody>
          {items.map((it) => (
            <tr key={it.name}>
              <td className="pr-3 text-muted-foreground">
                {it.color && (
                  <span
                    className="inline-block w-2 h-2 rounded-sm align-middle mr-1"
                    style={{ background: it.color }}
                  />
                )}
                {it.name}
              </td>
              <td className="text-right font-mono tabular-nums">
                {it.formatter(it.value as number | null)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function chartCard(title: string, subtitle: string | undefined, children: React.ReactNode) {
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
      <CardContent className="pt-2">{children}</CardContent>
    </Card>
  );
}

export function ForeignFuturesChart({ data }: { data: ForeignFuturesResponse }) {
  const rows: Row[] = useMemo(() => data.dates.map((d, i) => ({
    date: d,
    open:           data.candles[i]?.open  ?? null,
    high:           data.candles[i]?.high  ?? null,
    low:            data.candles[i]?.low   ?? null,
    close:          data.candles[i]?.close ?? null,
    cost:           data.cost[i] ?? null,
    net_position:   data.net_position[i] ?? null,
    net_change:     data.net_change[i] ?? null,
    unrealized_pnl: data.unrealized_pnl[i] ?? null,
    realized_pnl:   data.realized_pnl[i] ?? 0,
    retail_ratio:   data.retail_ratio?.[i] ?? null,
  })), [data]);

  const last = rows[rows.length - 1];
  const settlementSet = useMemo(
    () => new Set(data.settlement_dates),
    [data.settlement_dates],
  );

  const settlementLines = (
    <>
      {data.settlement_dates.map((d) => (
        <ReferenceLine
          key={d}
          x={d}
          stroke="#94a3b8"
          strokeDasharray="2 4"
          label={{ value: '結算', position: 'top', fontSize: 10, fill: '#64748b' }}
        />
      ))}
    </>
  );

  // Header subtitle for each region — current values like the reference image.
  const subtitleR1 = last
    ? `當日持倉成本 ${POINTS_FMT(last.cost)}`
    : undefined;
  const subtitleR2 = last
    ? `多空未平倉淨額 ${LOTS_FMT(last.net_position)} · 日變動 ${LOTS_FMT(last.net_change)}`
    : undefined;
  const subtitleR3 = last
    ? `未實現損益(萬元) ${TENK_FMT(last.unrealized_pnl)}`
    : undefined;
  const subtitleR4 = last
    ? `已實現損益(萬元) ${TENK_FMT(last.realized_pnl)}`
    : undefined;
  const subtitleR5 = last
    ? `當日散戶多空比 ${PCT_FMT(last.retail_ratio)}`
    : undefined;

  // Pre-compute settlement existence for ReferenceLine label suppression.
  void settlementSet;

  return (
    <div className="space-y-3">
      {chartCard('K 線 + 外資持倉成本', subtitleR1, (
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={rows} syncId={SYNC_ID}
            margin={{ top: 24, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" hide />
            <YAxis domain={['auto', 'auto']} width={60}
              tickFormatter={(v: number) => v.toLocaleString()} />
            <Tooltip content={<SharedTooltip />} />
            <Bar
              dataKey={(row: Row) =>
                row.low != null && row.high != null ? [row.low, row.high] : null
              }
              shape={<CandleShape />}
              isAnimationActive={false}
              legendType="none"
            />
            <Line dataKey="cost" stroke={COST_LINE} dot={false}
              strokeWidth={1.5} name="持倉成本" connectNulls />
            {settlementLines}
          </ComposedChart>
        </ResponsiveContainer>
      ))}

      {chartCard('多空未平倉口數淨額 + 日變動', subtitleR2, (
        <ResponsiveContainer width="100%" height={180}>
          <ComposedChart data={rows} syncId={SYNC_ID}
            margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" hide />
            <YAxis yAxisId="bar" orientation="left" width={60}
              tickFormatter={(v: number) => Math.round(v).toLocaleString()} />
            <YAxis yAxisId="line" orientation="right" width={60}
              tickFormatter={(v: number) => Math.round(v).toLocaleString()} />
            <Tooltip content={<SharedTooltip />} />
            <ReferenceLine yAxisId="bar" y={0} stroke="#94a3b8" />
            <Bar yAxisId="bar" dataKey="net_change" name="日變動">
              {rows.map((r) => (
                <Cell key={r.date}
                  fill={(r.net_change ?? 0) >= 0 ? POSITIVE : NEGATIVE} />
              ))}
            </Bar>
            <Line yAxisId="line" dataKey="net_position" stroke={NET_LINE}
              dot={false} strokeWidth={1.5} name="多空未平倉淨額" connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      ))}

      {chartCard('未實現損益(萬元)', subtitleR3, (
        <ResponsiveContainer width="100%" height={140}>
          <ComposedChart data={rows} syncId={SYNC_ID}
            margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" hide />
            <YAxis width={60}
              tickFormatter={(v: number) => Math.round(v / 10_000).toLocaleString()} />
            <Tooltip content={<SharedTooltip />} />
            <ReferenceLine y={0} stroke="#94a3b8" />
            <Bar dataKey="unrealized_pnl" name="未實現損益">
              {rows.map((r) => (
                <Cell key={r.date}
                  fill={(r.unrealized_pnl ?? 0) >= 0 ? POSITIVE : NEGATIVE} />
              ))}
            </Bar>
          </ComposedChart>
        </ResponsiveContainer>
      ))}

      {chartCard('已實現損益(萬元)', subtitleR4, (
        <ResponsiveContainer width="100%" height={140}>
          <ComposedChart data={rows} syncId={SYNC_ID}
            margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" hide />
            <YAxis width={60}
              tickFormatter={(v: number) => Math.round(v / 10_000).toLocaleString()} />
            <Tooltip content={<SharedTooltip />} />
            <ReferenceLine y={0} stroke="#94a3b8" />
            <Bar dataKey="realized_pnl" name="已實現損益">
              {rows.map((r) => (
                <Cell key={r.date}
                  fill={r.realized_pnl >= 0 ? POSITIVE : NEGATIVE} />
              ))}
            </Bar>
          </ComposedChart>
        </ResponsiveContainer>
      ))}

      {chartCard('散戶多空比 (%)', subtitleR5, (
        <ResponsiveContainer width="100%" height={160}>
          <ComposedChart data={rows} syncId={SYNC_ID}
            margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis width={60}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
            <Tooltip content={<SharedTooltip />} />
            <ReferenceLine y={0} stroke="#94a3b8" />
            <Line dataKey="retail_ratio" stroke={RETAIL_LINE} dot={false}
              strokeWidth={1.5} name="散戶多空比" connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      ))}
    </div>
  );
}
