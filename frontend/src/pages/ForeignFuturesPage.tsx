import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useForeignFutures } from '@/hooks/useForeignFutures';
import { ForeignFuturesChart } from '@/components/foreign-futures/ForeignFuturesChart';
import { ForeignSpotChart } from '@/components/foreign-futures/ForeignSpotChart';
import { ForeignOptionsAmountChart } from '@/components/foreign-futures/ForeignOptionsAmountChart';
import { ForeignOptionsDetailTable } from '@/components/foreign-futures/ForeignOptionsDetailTable';
import { ForeignOptionsStrikeDistribution } from '@/components/foreign-futures/ForeignOptionsStrikeDistribution';
import { ForeignFlowAiReport } from '@/components/foreign-futures/ForeignFlowAiReport';
import { RefreshDataButton } from '@/components/foreign-futures/RefreshDataButton';

const RANGES = ['1M', '3M', '6M', '1Y', '3Y'] as const;
type Range = (typeof RANGES)[number];

function isRange(v: string): v is Range {
  return (RANGES as readonly string[]).includes(v);
}

export default function ForeignFuturesPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get('range') || '3M';
  const range: Range = isRange(raw) ? raw : '3M';

  const { data, isLoading, isError } = useForeignFutures(range);
  const lastDate = data?.dates[data.dates.length - 1] ?? '';
  const lastClose = data?.candles[data.candles.length - 1]?.close;

  return (
    <div className="container mx-auto p-4 space-y-4">
      <Button asChild variant="ghost" size="sm" className="-ml-2 gap-1">
        <Link to="/futures/tw" aria-label="返回台指期詳情">
          <ArrowLeft className="h-4 w-4" />
          返回台指期
        </Link>
      </Button>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">台指期 · 外資動向</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {lastDate
              ? `最後交易日 ${lastDate}${
                  lastClose != null ? ' · 收 ' + lastClose.toLocaleString() : ''
                }`
              : '—'}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            持倉成本／未實現／已實現損益為近似值，與商業網站可能略有差異。
          </p>
        </div>
        <div className="flex items-start gap-2">
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
          <RefreshDataButton disabled={isLoading} />
        </div>
      </div>

      <ForeignFlowAiReport />

      {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
      {isError   && <p className="text-sm text-destructive">無法載入外資動向資料</p>}
      {data && data.dates.length > 0 && (
        <>
          <ForeignSpotChart data={data} />
          <ForeignFuturesChart data={data} />
          {data.options && (
            <>
              <ForeignOptionsAmountChart data={data} />
              <ForeignOptionsDetailTable data={data} />
              {data.options.oi_by_strike && (
                <ForeignOptionsStrikeDistribution data={data} />
              )}
            </>
          )}
        </>
      )}
      {data && data.dates.length === 0 && (
        <p className="text-sm text-muted-foreground">此區間尚無資料。</p>
      )}
    </div>
  );
}
