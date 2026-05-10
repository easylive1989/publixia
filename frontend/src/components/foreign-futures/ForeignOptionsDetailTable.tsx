import { useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import type {
  ForeignFuturesResponse,
  OptionsDetailRow,
  OptionsIdentity,
  OptionsPutCall,
} from '@/hooks/useForeignFutures';

const IDENTITY_LABEL: Record<OptionsIdentity, string> = {
  foreign:          '外資',
  investment_trust: '投信',
  dealer:           '自營商',
};
const IDENTITY_ORDER: OptionsIdentity[] = ['foreign', 'investment_trust', 'dealer'];

const LOTS_FMT = (v: number) => Math.round(v).toLocaleString();
const BILLIONS_FMT = (v: number) => (v / 100_000).toFixed(2);

function netClass(v: number): string {
  if (v > 0) return 'text-green-600';
  if (v < 0) return 'text-red-600';
  return '';
}

interface SubTableProps {
  putCall: OptionsPutCall;
  rows: OptionsDetailRow[];
}

function SubTable({ putCall, rows }: SubTableProps) {
  const byIdentity = new Map<OptionsIdentity, OptionsDetailRow>();
  for (const r of rows) {
    if (r.put_call === putCall) byIdentity.set(r.identity, r);
  }
  return (
    <div>
      <div className="text-sm font-medium mb-1">
        {putCall === 'CALL' ? '買權 (CALL)' : '賣權 (PUT)'}
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>身份別</TableHead>
            <TableHead className="text-right">多方 OI</TableHead>
            <TableHead className="text-right">空方 OI</TableHead>
            <TableHead className="text-right">OI 淨額</TableHead>
            <TableHead className="text-right">多方金額(億)</TableHead>
            <TableHead className="text-right">空方金額(億)</TableHead>
            <TableHead className="text-right">多空淨額(億)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {IDENTITY_ORDER.map((id) => {
            const r = byIdentity.get(id);
            if (!r) {
              return (
                <TableRow key={id}>
                  <TableCell>{IDENTITY_LABEL[id]}</TableCell>
                  <TableCell colSpan={6} className="text-right text-muted-foreground">
                    —
                  </TableCell>
                </TableRow>
              );
            }
            const oiNet = r.long_oi - r.short_oi;
            const amountNet = r.long_amount - r.short_amount;
            return (
              <TableRow key={id}>
                <TableCell className="font-medium">{IDENTITY_LABEL[id]}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {LOTS_FMT(r.long_oi)}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {LOTS_FMT(r.short_oi)}
                </TableCell>
                <TableCell className={`text-right font-mono tabular-nums ${netClass(oiNet)}`}>
                  {LOTS_FMT(oiNet)}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {BILLIONS_FMT(r.long_amount)}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {BILLIONS_FMT(r.short_amount)}
                </TableCell>
                <TableCell className={`text-right font-mono tabular-nums ${netClass(amountNet)}`}>
                  {BILLIONS_FMT(amountNet)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

export function ForeignOptionsDetailTable(
  { data }: { data: ForeignFuturesResponse },
) {
  const opt = data.options;

  // Dates that actually have detail rows; default to latest available.
  const availableDates = useMemo(() => {
    if (!opt) return [];
    return Object.keys(opt.detail_by_date).sort();
  }, [opt]);

  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const effectiveDate = selectedDate ?? availableDates[availableDates.length - 1] ?? null;

  if (!opt) return null;

  const rows = effectiveDate ? opt.detail_by_date[effectiveDate] ?? [] : [];

  return (
    <Card>
      <CardHeader className="pb-2 flex-row items-center justify-between gap-2 space-y-0">
        <div>
          <CardTitle className="text-base font-medium">
            TXO 三大法人 每日明細
          </CardTitle>
          <p className="text-xs text-muted-foreground mt-0.5">
            單位：口 / 億元；多空淨額 = 多方 − 空方
          </p>
        </div>
        {availableDates.length > 0 && effectiveDate && (
          <Select
            value={effectiveDate}
            onValueChange={(v) => setSelectedDate(v)}
          >
            <SelectTrigger className="w-[150px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[...availableDates].reverse().map((d) => (
                <SelectItem key={d} value={d}>{d}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </CardHeader>
      <CardContent className="pt-2 space-y-4">
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">此日無 TXO 三大法人資料。</p>
        ) : (
          <>
            <SubTable putCall="CALL" rows={rows} />
            <SubTable putCall="PUT"  rows={rows} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
