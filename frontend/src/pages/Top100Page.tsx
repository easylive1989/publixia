import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { useAutoTracked, type WatchlistRow } from '@/hooks/useWatchlist';
import { cn } from '@/lib/utils';

function fmtChange(n: number | null, suffix = ''): string {
  if (n == null) return '—';
  return (n >= 0 ? '+' : '') + n.toFixed(2) + suffix;
}

function changeClass(n: number | null): string | undefined {
  if (n == null) return undefined;
  return n >= 0 ? 'text-green-600' : 'text-red-600';
}

function Row({ row }: { row: WatchlistRow }) {
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
    </TableRow>
  );
}

export default function Top100Page() {
  const { data, isLoading, isError } = useAutoTracked();
  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold">台股市值百大</h1>
        <Link to="/" className="text-sm text-muted-foreground hover:underline">
          ← 返回 Dashboard
        </Link>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>
            前 100 大上市公司{data ? `(${data.length})` : ''}
          </CardTitle>
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
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((row) => (
                  <Row key={row.ticker} row={row} />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
