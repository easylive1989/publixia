import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { useBacktest, type BacktestResponse } from '@/hooks/useStrategy';
import { ApiError } from '@/lib/api-client';
import { EquityCurveChart } from './EquityCurveChart';

interface Props {
  strategyId: number;
}

function defaultRange(): { start: string; end: string } {
  const today = new Date();
  const start = new Date(today.getFullYear() - 5, today.getMonth(), today.getDate());
  return {
    start: start.toISOString().slice(0, 10),
    end:   today.toISOString().slice(0, 10),
  };
}

export function BacktestPanel({ strategyId }: Props) {
  const range = defaultRange();
  const [startDate, setStartDate] = useState(range.start);
  const [endDate,   setEndDate]   = useState(range.end);
  const [result,    setResult]    = useState<BacktestResponse | null>(null);
  const [error,     setError]     = useState<string | null>(null);

  const backtest = useBacktest(strategyId);

  const run = () => {
    setError(null);
    backtest.mutate(
      { start_date: startDate, end_date: endDate },
      {
        onSuccess: (r) => setResult(r),
        onError: (e: unknown) =>
          setError(e instanceof ApiError ? e.message : '回測失敗'),
      },
    );
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label htmlFor="bt-start" className="text-sm">開始日期</label>
          <Input
            id="bt-start"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="bt-end" className="text-sm">結束日期</label>
          <Input
            id="bt-end"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>
        <Button onClick={run} disabled={backtest.isPending}>
          {backtest.isPending ? '計算中…' : '執行回測'}
        </Button>
      </div>

      {error && <p className="text-destructive text-sm">{error}</p>}
      {result?.warnings.length ? (
        <ul className="text-amber-700 text-sm list-disc pl-5">
          {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      ) : null}

      {result && <BacktestSummaryCards summary={result.summary} />}
      {result && result.trades.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">累計權益曲線</CardTitle>
          </CardHeader>
          <CardContent>
            <EquityCurveChart trades={result.trades} />
          </CardContent>
        </Card>
      )}
      {result && result.trades.length > 0 && <BacktestTradesTable result={result} />}
    </div>
  );
}

function BacktestSummaryCards({ summary }: { summary: BacktestResponse['summary'] }) {
  const cards = [
    { label: '總損益 (NTD)',    value: summary.total_pnl_amount.toLocaleString() },
    { label: '勝率',           value: `${summary.win_rate.toFixed(1)}%` },
    { label: '交易次數',       value: summary.n_trades },
    { label: '平均持倉 (bars)', value: summary.avg_held_bars.toFixed(1) },
    { label: '盈虧比',         value: summary.profit_factor === 0 ? '—' : summary.profit_factor.toFixed(2) },
    { label: '最大回撤',       value: summary.max_drawdown_amt.toLocaleString() },
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
      {cards.map((c) => (
        <Card key={c.label}>
          <CardContent className="p-3">
            <p className="text-xs text-muted-foreground">{c.label}</p>
            <p className="text-lg font-semibold">{c.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function BacktestTradesTable({ result }: { result: BacktestResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">交易明細</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>進場日</TableHead>
              <TableHead className="text-right">進場價</TableHead>
              <TableHead>出場日</TableHead>
              <TableHead className="text-right">出場價</TableHead>
              <TableHead>原因</TableHead>
              <TableHead className="text-right">PnL (點)</TableHead>
              <TableHead className="text-right">PnL (NTD)</TableHead>
              <TableHead className="text-right">持倉 (bars)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {result.trades.map((t, i) => (
              <TableRow key={i}>
                <TableCell>{t.entry_date}</TableCell>
                <TableCell className="text-right">{t.entry_price.toLocaleString()}</TableCell>
                <TableCell>{t.exit_date}</TableCell>
                <TableCell className="text-right">{t.exit_price.toLocaleString()}</TableCell>
                <TableCell>{t.exit_reason}</TableCell>
                <TableCell className="text-right">{t.pnl_points.toFixed(2)}</TableCell>
                <TableCell className="text-right">{t.pnl_amount.toLocaleString()}</TableCell>
                <TableCell className="text-right">{t.held_bars}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
