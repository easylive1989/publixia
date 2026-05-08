import { useMemo, useState } from 'react';
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useDashboardData } from '@/hooks/useDashboardData';
import { useIndicatorHistory } from '@/hooks/useIndicatorHistory';
import { useRangeStore } from '@/store/range-store';
import { registerCard } from './registry';

type SeriesKey = 'foreign' | 'trust' | 'dealer';

const SERIES: Record<SeriesKey, { label: string; colour: string; indicator: string }> = {
  foreign: { label: '外資', colour: '#3b82f6', indicator: 'total_foreign_net' },
  trust:   { label: '投信', colour: '#16a34a', indicator: 'total_trust_net'   },
  dealer:  { label: '自營', colour: '#f97316', indicator: 'total_dealer_net'  },
};

interface Point {
  date: string;
  foreign: number | null;
  trust:   number | null;
  dealer:  number | null;
}

function fmtSigned(v: number): string {
  return (v >= 0 ? '+' : '') + v.toFixed(2) + ' 億';
}

function colourClass(v: number): string {
  return v >= 0 ? 'text-green-600' : 'text-red-600';
}

function ThreeInvestorsCard() {
  const range = useRangeStore((s) => s.range);
  const foreign = useIndicatorHistory(SERIES.foreign.indicator, range);
  const trust   = useIndicatorHistory(SERIES.trust.indicator,   range);
  const dealer  = useIndicatorHistory(SERIES.dealer.indicator,  range);
  const { data: snap } = useDashboardData();

  // Local toggle state. Clicking a Legend item flips its visibility;
  // the line stays in the chart so the legend symbol remains rendered
  // for re-toggling.
  const [visible, setVisible] = useState<Record<SeriesKey, boolean>>({
    foreign: true, trust: true, dealer: true,
  });

  const merged = useMemo<Point[]>(() => {
    const map = new Map<string, Point>();
    function pour(rows: { timestamp: string; value: number }[] | undefined,
                  key: SeriesKey) {
      for (const p of rows ?? []) {
        const date = p.timestamp.slice(0, 10);
        const e: Point = map.get(date) ?? { date, foreign: null, trust: null, dealer: null };
        e[key] = p.value;
        map.set(date, e);
      }
    }
    pour(foreign.data, 'foreign');
    pour(trust.data,   'trust');
    pour(dealer.data,  'dealer');
    return [...map.values()].sort((a, b) => a.date.localeCompare(b.date));
  }, [foreign.data, trust.data, dealer.data]);

  const isLoading = foreign.isLoading || trust.isLoading || dealer.isLoading;
  const isError   = foreign.isError   || trust.isError   || dealer.isError;

  const today: Record<SeriesKey, number | null> = {
    foreign: snap?.[SERIES.foreign.indicator]?.value ?? null,
    trust:   snap?.[SERIES.trust.indicator]?.value   ?? null,
    dealer:  snap?.[SERIES.dealer.indicator]?.value  ?? null,
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          三大法人淨買超 (億)
        </CardTitle>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs pt-1">
          {(Object.keys(SERIES) as SeriesKey[]).map((k) => {
            const v = today[k];
            return (
              <span key={k} className="text-muted-foreground">
                {SERIES[k].label}{' '}
                {v == null
                  ? <span className="text-muted-foreground">—</span>
                  : <strong className={colourClass(v)}>{fmtSigned(v)}</strong>}
              </span>
            );
          })}
        </div>
      </CardHeader>
      <CardContent className="space-y-1">
        {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
        {isError && <p className="text-sm text-destructive">無法載入</p>}
        {!isLoading && !isError && merged.length >= 2 && (
          <div className="h-64 pt-1" data-testid="spark">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={merged} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10, fill: '#71717a' }} width={60}
                       tickFormatter={(v: number) => v.toFixed(0)} />
                <ReferenceLine y={0} stroke="#71717a" />
                <Tooltip
                  formatter={(v) =>
                    typeof v === 'number' ? fmtSigned(v) : String(v ?? '')
                  }
                  labelFormatter={(d) => `日期:${d}`}
                />
                <Legend
                  onClick={(e) => {
                    const key = e.dataKey as SeriesKey | undefined;
                    if (key && key in visible) {
                      setVisible((v) => ({ ...v, [key]: !v[key] }));
                    }
                  }}
                />
                {(Object.keys(SERIES) as SeriesKey[]).map((k) => (
                  <Line
                    key={k}
                    type="monotone"
                    dataKey={k}
                    name={SERIES[k].label}
                    stroke={SERIES[k].colour}
                    strokeOpacity={visible[k] ? 1 : 0.15}
                    dot={false}
                    isAnimationActive={false}
                    hide={!visible[k]}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'total_three_investors',
  label: '三大法人淨買超',
  defaultPage: 'dashboard',
  component: ThreeInvestorsCard,
  cols: 2,
});
