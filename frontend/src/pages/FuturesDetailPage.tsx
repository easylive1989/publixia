import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useFuturesHistory } from '@/hooks/useFuturesHistory';
import { flattenHistory } from '@/lib/flatten-history';
import {
  KLineChart, VolumeChart, RSIChart, MACDChart,
} from '@/components/charts/PriceCharts';

const RANGES = ['3M', '6M', '1Y', '3Y', '5Y'] as const;
type FuturesRange = (typeof RANGES)[number];

function isRange(v: string): v is FuturesRange {
  return (RANGES as readonly string[]).includes(v);
}

export default function FuturesDetailPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get('range') || '1Y';
  const range: FuturesRange = isRange(raw) ? raw : '1Y';

  const { data, isLoading, isError } = useFuturesHistory(range);
  const rows = useMemo(
    () => (data ? flattenHistory({ ...data, ticker: data.symbol }) : []),
    [data],
  );

  const lastDate = data?.dates[data.dates.length - 1] ?? '';
  const lastClose = data?.candles[data.candles.length - 1]?.close;

  return (
    <div className="container mx-auto p-4 space-y-4">
      <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1">
        <Link to="/" aria-label="返回 dashboard">
          <ArrowLeft className="h-4 w-4" />
          返回 Dashboard
        </Link>
      </Button>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">台指期 (TX) · 近月連續</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {lastDate
              ? `最後交易日 ${lastDate}${
                  lastClose != null ? ' · 收 ' + lastClose.toLocaleString() : ''
                } · TWD`
              : '—'}
          </p>
        </div>
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <Button
              key={r}
              size="sm"
              variant={r === range ? 'default' : 'outline'}
              onClick={() => setParams({ range: r })}
            >
              {r}
            </Button>
          ))}
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
      {isError && <p className="text-sm text-destructive">無法載入歷史資料</p>}
      {data && rows.length > 0 && (
        <div className="space-y-4">
          <KLineChart rows={rows} />
          <VolumeChart rows={rows} />
          <MACDChart rows={rows} />
          <RSIChart rows={rows} />
        </div>
      )}
    </div>
  );
}
