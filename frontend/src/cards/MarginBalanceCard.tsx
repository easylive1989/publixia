import {
  Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useDashboardData } from '@/hooks/useDashboardData';
import { useIndicatorHistory, type HistoryPoint } from '@/hooks/useIndicatorHistory';
import { useRangeStore } from '@/store/range-store';
import { registerCard } from './registry';

const MARGIN_STROKE = '#3b82f6'; // blue — 融資
const SHORT_STROKE  = '#ef4444'; // red  — 融券

interface MergedPoint {
  timestamp: string;
  margin?: number;
  short?:  number;
  ratio?:  number;
}

// Same shape as dashboard-cards.tsx — duplicated locally so the two files
// stay independent.
function fmtNextUpdate(iso: string | null | undefined): string {
  if (!iso) return '';
  const m = iso.match(/^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return '';
  const [, mm, dd, hh, mi] = m;
  return `${mm}-${dd} ${hh}:${mi}`;
}

function mergeByDate(
  margin?: HistoryPoint[],
  short?:  HistoryPoint[],
  ratio?:  HistoryPoint[],
): MergedPoint[] {
  const byDate = new Map<string, MergedPoint>();
  const pour = (
    rows: HistoryPoint[] | undefined,
    key: 'margin' | 'short' | 'ratio',
  ) => {
    for (const p of rows ?? []) {
      const slot = byDate.get(p.timestamp) ?? { timestamp: p.timestamp };
      slot[key] = p.value;
      byDate.set(p.timestamp, slot);
    }
  };
  pour(margin, 'margin');
  pour(short,  'short');
  pour(ratio,  'ratio');
  return [...byDate.values()].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
}

function tooltipContent({ active, payload, label }: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: MergedPoint }>;
  label?: unknown;
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0]?.payload;
  if (!p) return null;
  return (
    <div className="rounded border bg-background px-2 py-1 text-xs shadow-sm space-y-0.5">
      <div className="text-muted-foreground">{String(label).slice(0, 10)}</div>
      {p.margin !== undefined && (
        <div className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: MARGIN_STROKE }} />
          <span>融資餘額</span>
          <span className="ml-auto font-medium tabular-nums">
            {p.margin.toLocaleString()} 億
          </span>
        </div>
      )}
      {p.short !== undefined && (
        <div className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: SHORT_STROKE }} />
          <span>融券餘額</span>
          <span className="ml-auto font-medium tabular-nums">
            {(p.short / 1000).toFixed(0)} 千張
          </span>
        </div>
      )}
      {p.ratio !== undefined && (
        <div className="flex items-center gap-2">
          <span className="inline-block h-2 w-2" />
          <span>券資比</span>
          <span className="ml-auto font-medium tabular-nums">
            {p.ratio.toFixed(2)} %
          </span>
        </div>
      )}
    </div>
  );
}

function MarginBalanceCard() {
  const range  = useRangeStore((s) => s.range);
  const margin = useIndicatorHistory('margin_balance',      range);
  const short  = useIndicatorHistory('short_balance',       range);
  const ratio  = useIndicatorHistory('short_margin_ratio',  range);
  const dash   = useDashboardData();

  const series     = mergeByDate(margin.data, short.data, ratio.data);
  const nextUpdate = fmtNextUpdate(dash.data?.margin_balance?.next_update_at);

  const isLoading = margin.isLoading || short.isLoading;
  const isError   = margin.isError   || short.isError;
  const hasChart  = series.length >= 2;

  return (
    <Card className="h-full">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          融資 / 融券餘額
        </CardTitle>
        {nextUpdate && (
          <span className="text-xs text-muted-foreground">下次更新 {nextUpdate}</span>
        )}
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: MARGIN_STROKE }} />
            融資餘額（億）
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: SHORT_STROKE }} />
            融券餘額（千張）
          </span>
        </div>

        {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
        {isError   && <p className="text-sm text-destructive">無法載入</p>}
        {!isLoading && !isError && !hasChart && (
          <p className="text-sm text-muted-foreground">尚無資料</p>
        )}
        {hasChart && (
          <div className="h-48" data-testid="margin-short-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <XAxis dataKey="timestamp" hide />
                <YAxis
                  yAxisId="margin"
                  orientation="left"
                  domain={['auto', 'auto']}
                  width={56}
                  tick={{ fontSize: 10, fill: '#71717a' }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => v.toLocaleString()}
                />
                <YAxis
                  yAxisId="short"
                  orientation="right"
                  domain={['auto', 'auto']}
                  width={48}
                  tick={{ fontSize: 10, fill: '#71717a' }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => (v / 1000).toFixed(0)}
                />
                <Tooltip
                  cursor={{ stroke: '#a1a1aa', strokeWidth: 1 }}
                  content={tooltipContent}
                />
                <Line
                  yAxisId="margin"
                  type="monotone"
                  dataKey="margin"
                  stroke={MARGIN_STROKE}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                />
                <Line
                  yAxisId="short"
                  type="monotone"
                  dataKey="short"
                  stroke={SHORT_STROKE}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'margin_short',
  label: '融資 / 融券餘額',
  defaultPage: 'dashboard',
  component: MarginBalanceCard,
  cols: 2,
});
