import { listCards } from '@/cards/registry';
import { useCardPrefsStore } from '@/store/card-prefs-store';
import { RANGES, useRangeStore, type RangeKey } from '@/store/range-store';
import { DashboardSettingsDialog } from '@/components/DashboardSettingsDialog';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { StrategiesNavLink } from '@/components/strategy/NavLink';
import { Top100NavLink } from '@/components/top100/NavLink';

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
  const allCards = listCards('dashboard');
  const hiddenIds = useCardPrefsStore((s) => s.hiddenIds);
  const visible = allCards.filter((c) => !hiddenIds.has(c.id));

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <StrategiesNavLink />
          <Top100NavLink />
        </div>
        <DashboardSettingsDialog />
      </div>
      <RangeBar />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {visible.map(({ id, component: Card, cols = 1 }) => (
          <div
            key={id}
            className={cn(
              'relative h-full',
              cols === 3 && 'lg:col-span-3',
              cols === 2 && 'lg:col-span-2',
            )}
          >
            <Card />
          </div>
        ))}
      </div>
    </div>
  );
}
