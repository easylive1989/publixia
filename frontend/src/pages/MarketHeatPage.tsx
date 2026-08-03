import { useState } from 'react';
import { HeatTable } from '@/components/HeatTable';
import { MarketHeat } from '@/components/MarketHeat';
import { useMarketHeat } from '@/hooks/useMarketHeat';

// 區間以交易日計：一月 ~22、一季 ~66、半年 ~130、一年 ~240。
const RANGES: { label: string; days: number | null }[] = [
  { label: '近一月', days: 22 },
  { label: '近一季', days: 66 },
  { label: '近半年', days: 130 },
  { label: '近一年', days: 240 },
  { label: '全部', days: null },
];

export default function MarketHeatPage() {
  const [days, setDays] = useState<number | null>(240);
  const heat = useMarketHeat(days);

  return (
    <main className="wrap">
      <div className="filters" role="tablist" aria-label="區間">
        {RANGES.map((r) => (
          <button
            key={r.label}
            role="tab"
            aria-selected={days === r.days}
            className={`tab${days === r.days ? ' on' : ''}`}
            onClick={() => setDays(r.days)}
          >
            {r.label}
          </button>
        ))}
      </div>
      <MarketHeat data={heat.data} isLoading={heat.isLoading} />
      <HeatTable rows={heat.data?.days ?? []} />
    </main>
  );
}
