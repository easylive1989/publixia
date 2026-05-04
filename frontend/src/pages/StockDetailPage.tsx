import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { listCards } from '@/cards/registry';
import { useStockHistory } from '@/hooks/useStockHistory';

const RANGES = ['1M', '3M', '6M', '1Y', '3Y'] as const;

export default function StockDetailPage() {
  const { code = '' } = useParams<{ code: string }>();
  const [params, setParams] = useSearchParams();
  const range = params.get('range') || '3M';
  const { data, isLoading, isError } = useStockHistory();
  const cards = listCards('stock');

  const lastDate = data?.dates[data.dates.length - 1] ?? '';
  const titleSub = lastDate
    ? `最後資料日 ${lastDate}${data?.currency ? ' · ' + data.currency : ''}`
    : '';

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
          <h1 className="text-2xl font-bold">
            {code}{data?.name && ` · ${data.name}`}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">{titleSub}</p>
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
      {data && (
        <div className="space-y-4">
          {cards.map(({ id, component: Card }) => <Card key={id} />)}
        </div>
      )}
    </div>
  );
}
