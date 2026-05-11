import { useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Legend, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import type { ForeignFuturesResponse } from '@/hooks/useForeignFutures';
import { POSITIVE, NEGATIVE } from './colors';

interface StrikeRow {
  strike: number;
  strikeLabel: string;
  call_oi: number;
  put_oi: number;
}

const LOTS_FMT = (v: number) => Math.round(v).toLocaleString();

function formatExpiry(expiry: string): string {
  // '202506' → '2025/06'; '202506W2' → '2025/06 W2'
  const m = expiry.match(/^(\d{4})(\d{2})(.*)$/);
  if (!m) return expiry;
  const week = m[3] ? ` ${m[3]}` : '';
  return `${m[1]}/${m[2]}${week}`;
}

function StrikeTooltip({ active, label, payload }: any) {
  if (!active || !payload?.length) return null;
  const row: StrikeRow | undefined = payload[0]?.payload;
  if (!row) return null;
  const total = row.call_oi + row.put_oi;
  return (
    <div className="rounded-md border bg-background/95 px-3 py-2 text-xs shadow-md">
      <div className="font-medium mb-1">履約價 {label}</div>
      <table className="border-separate [border-spacing:0_2px]">
        <tbody>
          <tr>
            <td className="pr-3 text-muted-foreground">
              <span
                className="inline-block w-2 h-2 rounded-sm align-middle mr-1"
                style={{ background: POSITIVE }}
              />
              買權 OI
            </td>
            <td className="text-right font-mono tabular-nums">
              {LOTS_FMT(row.call_oi)}
            </td>
          </tr>
          <tr>
            <td className="pr-3 text-muted-foreground">
              <span
                className="inline-block w-2 h-2 rounded-sm align-middle mr-1"
                style={{ background: NEGATIVE }}
              />
              賣權 OI
            </td>
            <td className="text-right font-mono tabular-nums">
              {LOTS_FMT(row.put_oi)}
            </td>
          </tr>
          <tr>
            <td className="pr-3 text-muted-foreground">合計</td>
            <td className="text-right font-mono tabular-nums">
              {LOTS_FMT(total)}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function ForeignOptionsStrikeDistribution(
  { data }: { data: ForeignFuturesResponse },
) {
  const block = data.options?.oi_by_strike;
  const lastClose = data.candles[data.candles.length - 1]?.close ?? null;

  const [selectedExpiry, setSelectedExpiry] = useState<string | null>(null);
  const effectiveExpiry = useMemo(() => {
    if (!block) return null;
    if (selectedExpiry && block.by_expiry[selectedExpiry]) return selectedExpiry;
    if (block.near_month && block.by_expiry[block.near_month]) {
      return block.near_month;
    }
    return block.expiry_months[0] ?? null;
  }, [block, selectedExpiry]);

  const rows: StrikeRow[] = useMemo(() => {
    if (!block || !effectiveExpiry) return [];
    const slice = block.by_expiry[effectiveExpiry];
    if (!slice) return [];
    return slice.strikes.map((s, i) => ({
      strike: s,
      strikeLabel: Number.isInteger(s) ? String(s) : s.toString(),
      call_oi: slice.call_oi[i] ?? 0,
      put_oi:  slice.put_oi[i]  ?? 0,
    }));
  }, [block, effectiveExpiry]);

  // Filter out far-OTM strikes with zero OI on both sides so the chart
  // doesn't waste pixels on dead series. Keep a window around the live
  // OI band: trim leading/trailing zero rows.
  const trimmed = useMemo(() => {
    if (rows.length === 0) return rows;
    let start = 0;
    while (start < rows.length
      && rows[start].call_oi === 0 && rows[start].put_oi === 0) {
      start += 1;
    }
    let end = rows.length - 1;
    while (end > start
      && rows[end].call_oi === 0 && rows[end].put_oi === 0) {
      end -= 1;
    }
    return rows.slice(start, end + 1);
  }, [rows]);

  if (!block) return null;

  const hasData = trimmed.length > 0;
  const totals = useMemo(() => {
    let call = 0;
    let put = 0;
    for (const r of trimmed) {
      call += r.call_oi;
      put += r.put_oi;
    }
    return { call, put };
  }, [trimmed]);

  // Closest strike to current spot, used for a vertical reference line
  // so the reader can immediately see ATM vs OTM stacking.
  const refStrike: number | null = useMemo(() => {
    if (lastClose == null || trimmed.length === 0) return null;
    let best = trimmed[0].strike;
    let bestDelta = Math.abs(best - lastClose);
    for (const r of trimmed) {
      const delta = Math.abs(r.strike - lastClose);
      if (delta < bestDelta) {
        bestDelta = delta;
        best = r.strike;
      }
    }
    return best;
  }, [trimmed, lastClose]);

  return (
    <Card>
      <CardHeader className="pb-2 flex-row items-start justify-between gap-2 space-y-0">
        <div>
          <CardTitle className="text-base font-medium">
            各履約價未平倉量 (OI) 分布
          </CardTitle>
          <p className="text-xs text-muted-foreground mt-0.5">
            {block.date
              ? `市場合計 · ${block.date}`
              : '尚無 TXO 各履約價未沖銷量資料'}
            {lastClose != null && block.date
              ? ` · 期指收 ${lastClose.toLocaleString()}`
              : ''}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            單位：口；TAIFEX 不公開身份別 (外資/投信/自營) 各履約價數據，
            此圖為全市場合計。
          </p>
        </div>
        {block.expiry_months.length > 0 && effectiveExpiry && (
          <Select
            value={effectiveExpiry}
            onValueChange={(v) => setSelectedExpiry(v)}
          >
            <SelectTrigger className="w-[150px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {block.expiry_months.map((m) => (
                <SelectItem key={m} value={m}>{formatExpiry(m)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </CardHeader>
      <CardContent className="pt-2">
        {!hasData ? (
          <p className="text-sm text-muted-foreground">
            此到期月份無 OI 資料。
          </p>
        ) : (
          <>
            <p className="text-xs text-muted-foreground mb-2">
              {effectiveExpiry && `到期 ${formatExpiry(effectiveExpiry)} · `}
              買權合計 {LOTS_FMT(totals.call)} 口 · 賣權合計 {LOTS_FMT(totals.put)} 口
            </p>
            <ResponsiveContainer width="100%" height={320}>
              <BarChart
                data={trimmed}
                margin={{ top: 8, right: 12, left: 0, bottom: 24 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="strikeLabel"
                  interval="preserveStartEnd"
                  angle={-45}
                  textAnchor="end"
                  height={48}
                  tick={{ fontSize: 11 }}
                />
                <YAxis width={70}
                  tickFormatter={(v: number) => v.toLocaleString()} />
                <Tooltip content={<StrikeTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {refStrike != null && (
                  <ReferenceLine
                    x={String(refStrike)}
                    stroke="#94a3b8"
                    strokeDasharray="2 4"
                    label={{
                      value: '現價',
                      position: 'top',
                      fontSize: 10,
                      fill: '#64748b',
                    }}
                  />
                )}
                <Bar dataKey="call_oi" fill={POSITIVE} name="買權 OI" />
                <Bar dataKey="put_oi"  fill={NEGATIVE} name="賣權 OI" />
              </BarChart>
            </ResponsiveContainer>
          </>
        )}
      </CardContent>
    </Card>
  );
}
