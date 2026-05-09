import { useState } from 'react';
import { Link } from 'react-router-dom';
import { X } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useAddStock, useDeleteStock, useWatchlist, type WatchlistRow } from '@/hooks/useWatchlist';
import { cn } from '@/lib/utils';
import { registerCard } from './registry';

function fmtChange(n: number | null, suffix = ''): string {
  if (n == null) return '—';
  return (n >= 0 ? '+' : '') + n.toFixed(2) + suffix;
}

function changeClass(n: number | null): string | undefined {
  if (n == null) return undefined;
  return n >= 0 ? 'text-green-600' : 'text-red-600';
}

function Row({
  row, onDelete, deleting,
}: { row: WatchlistRow; onDelete: (t: string) => void; deleting: boolean }) {
  return (
    <TableRow>
      <TableCell>
        <Link to={`/stock/${row.ticker}`} className="font-medium hover:underline">
          {row.ticker}
        </Link>
      </TableCell>
      <TableCell>{row.name}</TableCell>
      <TableCell className="text-right">
        {row.price != null
          ? row.price.toLocaleString() + (row.currency ? ' ' + row.currency : '')
          : '—'}
      </TableCell>
      <TableCell className={cn('text-right', changeClass(row.change))}>
        {fmtChange(row.change)}
      </TableCell>
      <TableCell className={cn('text-right', changeClass(row.change_pct))}>
        {fmtChange(row.change_pct, '%')}
      </TableCell>
      <TableCell className="text-right">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onDelete(row.ticker)}
          disabled={deleting}
          aria-label={`移除 ${row.ticker}`}
        >
          <X className="h-4 w-4" />
        </Button>
      </TableCell>
    </TableRow>
  );
}

function AddForm() {
  const [value, setValue] = useState('');
  const add = useAddStock();
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = value.trim().toUpperCase();
    if (!t) return;
    add.mutate(t, { onSuccess: () => setValue('') });
  };
  return (
    <form onSubmit={submit} className="flex gap-2 pt-3">
      <Input
        placeholder="輸入代號，例如 2317.TW、AAPL、ETH-USD"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={add.isPending}
      />
      <Button type="submit" disabled={add.isPending}>+ 新增</Button>
    </form>
  );
}

function WatchlistCard() {
  const { data, isLoading, isError } = useWatchlist();
  const del = useDeleteStock();
  return (
    <Card>
      <CardHeader>
        <CardTitle>自選股票</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
        {isError && <p className="text-sm text-destructive">無法載入</p>}
        {data && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>代號</TableHead>
                <TableHead>名稱</TableHead>
                <TableHead className="text-right">價格</TableHead>
                <TableHead className="text-right">漲跌</TableHead>
                <TableHead className="text-right">漲跌幅</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row) => (
                <Row
                  key={row.ticker}
                  row={row}
                  onDelete={(t) => del.mutate(t)}
                  deleting={del.isPending && del.variables === row.ticker}
                />
              ))}
            </TableBody>
          </Table>
        )}
        <AddForm />
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'watchlist',
  label: '自選股票',
  defaultPage: 'dashboard',
  component: WatchlistCard,
  cols: 2,
});
