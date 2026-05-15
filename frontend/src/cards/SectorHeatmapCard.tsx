import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { useSectorHeatmap } from '@/hooks/useSectorHeatmap';
import { registerCard } from './registry';

function formatDateShort(iso: string): string {
  // "2026-05-15" → "5/15"
  const [, m, d] = iso.split('-');
  return `${parseInt(m, 10)}/${parseInt(d, 10)}`;
}

function cellClass(pct: number | null): string {
  if (pct === null || pct === undefined) {
    return 'bg-gray-100 text-gray-400';
  }
  if (pct <= -0.2) return 'bg-red-500 text-white';
  if (pct <= -0.1) return 'bg-red-300 text-red-900';
  if (pct >= 0.2)  return 'bg-blue-800 text-white';
  if (pct >= 0.1)  return 'bg-blue-400 text-white';
  return 'bg-gray-200 text-gray-700';
}

function formatPct(pct: number | null): string {
  if (pct === null || pct === undefined) return '—';
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${(pct * 100).toFixed(1)}%`;
}

function SectorHeatmapCard() {
  const { data, isLoading, isError } = useSectorHeatmap({ days: 5, topN: 10 });

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          族群量能熱力圖（產業別）
        </CardTitle>
        <p className="text-xs text-muted-foreground pt-1">
          每格為當日總成交值相對過去 20 交易日均之 % 變化
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
        {isError && <p className="text-sm text-destructive">無法載入</p>}
        {data && data.groups.length === 0 && (
          <p className="text-sm text-muted-foreground">尚無資料</p>
        )}
        {data && data.groups.length > 0 && (
          <>
            <div
              className="grid gap-1 text-xs"
              style={{
                gridTemplateColumns: `minmax(5rem, 7rem) repeat(${data.days.length}, minmax(0, 1fr))`,
              }}
            >
              <div />
              {data.days.map((d) => (
                <div
                  key={d}
                  className="text-center text-muted-foreground font-medium pb-1"
                >
                  {formatDateShort(d)}
                </div>
              ))}
              {data.groups.map((g) => (
                <Row key={g.code} name={g.name} pcts={g.pct_series} />
              ))}
            </div>
            <Legend />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Row({ name, pcts }: { name: string; pcts: Array<number | null> }) {
  return (
    <>
      <div className="truncate py-1.5 text-foreground font-medium" title={name}>
        {name}
      </div>
      {pcts.map((p, i) => (
        <div
          key={i}
          className={cn(
            'rounded text-center py-1.5 font-medium tabular-nums',
            cellClass(p),
          )}
        >
          {formatPct(p)}
        </div>
      ))}
    </>
  );
}

function Legend() {
  const items: Array<[string, string]> = [
    ['bg-red-500',  '≤ −20%'],
    ['bg-red-300',  '−10%'],
    ['bg-gray-200', '持平'],
    ['bg-blue-400', '+10%'],
    ['bg-blue-800', '≥ +20%'],
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
      <span>縮量</span>
      {items.map(([cls, label]) => (
        <span key={cls} className="flex items-center gap-1">
          <span className={cn('inline-block w-3 h-3 rounded-sm', cls)} />
          {label}
        </span>
      ))}
      <span>放量</span>
    </div>
  );
}

registerCard({
  id: 'sector_heatmap_industry',
  label: '族群量能熱力圖',
  defaultPage: 'dashboard',
  component: SectorHeatmapCard,
  cols: 2,
  rows: 2,
});
