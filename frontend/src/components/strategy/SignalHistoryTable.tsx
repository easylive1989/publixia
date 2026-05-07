import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import type { SignalRecord } from '@/hooks/useStrategy';

const KIND_LABELS: Record<SignalRecord['kind'], string> = {
  ENTRY_SIGNAL:  '📈 進場訊號',
  ENTRY_FILLED:  '✅ 進場結算',
  EXIT_SIGNAL:   '⚠️ 出場訊號',
  EXIT_FILLED:   '🏁 出場結算',
  MANUAL_RESET:  '🔧 手動重置',
  RUNTIME_ERROR: '❌ 執行錯誤',
};

export function SignalHistoryTable({ signals }: { signals: SignalRecord[] }) {
  if (!signals.length) {
    return (
      <p className="text-sm text-muted-foreground">
        尚無訊號歷史。
      </p>
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>類型</TableHead>
          <TableHead>日期</TableHead>
          <TableHead className="text-right">close</TableHead>
          <TableHead className="text-right">成交價</TableHead>
          <TableHead>原因</TableHead>
          <TableHead className="text-right">PnL (點)</TableHead>
          <TableHead className="text-right">PnL (NTD)</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {signals.map((s) => (
          <TableRow key={s.id}>
            <TableCell>{KIND_LABELS[s.kind] ?? s.kind}</TableCell>
            <TableCell>{s.signal_date}</TableCell>
            <TableCell className="text-right">
              {s.close_at_signal !== null ? s.close_at_signal.toLocaleString() : '—'}
            </TableCell>
            <TableCell className="text-right">
              {s.fill_price !== null ? s.fill_price.toLocaleString() : '—'}
            </TableCell>
            <TableCell>{s.exit_reason ?? '—'}</TableCell>
            <TableCell className="text-right">
              {s.pnl_points !== null ? s.pnl_points.toFixed(2) : '—'}
            </TableCell>
            <TableCell className="text-right">
              {s.pnl_amount !== null ? s.pnl_amount.toLocaleString() : '—'}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
