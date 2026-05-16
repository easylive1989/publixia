import { getCard, type CardSpec } from '@/cards/registry';
import { RANGES, useRangeStore, type RangeKey } from '@/store/range-store';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { AiReportNavLink, ForeignFuturesNavLink } from '@/components/foreign-futures/NavLink';

// Single source of truth for dashboard layout. Cards render in this exact
// order using each card's own cols/rows; CSS grid auto-flow places them.
// Adding a card means: register it in cards/, then append its id here.
const DASHBOARD_CARD_ORDER = [
  'news',                    // (1×2)
  'sector_heatmap_industry', // (2×2)
  'taiex',                   // (1×1)
  'total_three_investors',   // (2×1)
  'tw_volume',               // (1×1)
  'fear_greed',              // (1×1)
  'ndc',                     // (1×1)
  'margin_balance',          // (1×1)
  'short_balance',           // (1×1)
  'short_margin_ratio',      // (1×1)
  'fx',                      // (1×1)
] as const;

const RANGE_LABELS: Record<RangeKey, string> = {
  '1M': '1 個月',
  '3M': '3 個月',
  '6M': '6 個月',
  '1Y': '1 年',
  '3Y': '3 年',
};

function RangeBar() {
  const range = useRangeStore((s) => s.range);
  const setRange = useRangeStore((s) => s.setRange);
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-muted-foreground">時間區間</span>
      <div className="inline-flex flex-wrap gap-1" role="tablist" aria-label="時間區間">
        {RANGES.map((r) => (
          <Button
            key={r}
            type="button"
            size="sm"
            role="tab"
            aria-selected={range === r}
            variant={range === r ? 'default' : 'outline'}
            onClick={() => setRange(r)}
          >
            {RANGE_LABELS[r]}
          </Button>
        ))}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const cards = DASHBOARD_CARD_ORDER
    .map((id) => getCard(id))
    .filter((c): c is CardSpec => c !== undefined);

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <ForeignFuturesNavLink />
        <AiReportNavLink />
      </div>
      <RangeBar />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {cards.map(({ id, component: Card, cols = 1, rows = 1 }) => (
          <div
            key={id}
            className={cn(
              'relative h-full',
              cols === 3 && 'lg:col-span-3',
              cols === 2 && 'lg:col-span-2',
              rows === 2 && 'sm:row-span-2',
            )}
          >
            <Card />
          </div>
        ))}
      </div>
    </div>
  );
}
