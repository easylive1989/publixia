import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export interface BadgeInfo {
  text: string;
  tone: 'up' | 'down' | 'neutral';
}

export interface SparkPoint {
  timestamp: string;
  value: number;
}

interface Props {
  title: string;
  value?: string;
  sub?: string;
  nextUpdate?: string;
  badge?: BadgeInfo | null;
  valueClass?: string;
  loading?: boolean;
  error?: string;
  series?: SparkPoint[];
  formatSparkValue?: (v: number) => string;
}

const TONE_CLASS: Record<BadgeInfo['tone'], string> = {
  up:      'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200',
  down:    'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200',
  neutral: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200',
};

const SPARK_STROKE = '#3b82f6';

export function IndicatorCardView({
  title, value, sub, nextUpdate, badge, valueClass, loading, error, series, formatSparkValue,
}: Props) {
  const hasSpark = !!series && series.length >= 2;
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        {badge && (
          <span className={cn('rounded px-2 py-0.5 text-xs', TONE_CLASS[badge.tone])}>
            {badge.text}
          </span>
        )}
      </CardHeader>
      <CardContent className="space-y-1">
        {loading && <p className="text-sm text-muted-foreground">載入中…</p>}
        {error && <p className="text-sm text-destructive">{error}</p>}
        {!loading && !error && value !== undefined && (
          <p className={cn('text-2xl font-bold', valueClass)}>{value}</p>
        )}
        {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
        {nextUpdate && (
          <p className="text-xs text-muted-foreground">下次更新 {nextUpdate}</p>
        )}
        {hasSpark && (
          <div className="h-40 pt-1" data-testid="spark">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <XAxis dataKey="timestamp" hide />
                <YAxis
                  domain={['auto', 'auto']}
                  width={100}
                  tick={{ fontSize: 10, fill: '#71717a' }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => {
                    // Avoid recharts' SVG word-wrap by replacing the space
                    // between value and unit with a non-breaking space.
                    const formatted = formatSparkValue
                      ? formatSparkValue(v)
                      : v.toLocaleString();
                    return formatted.replace(/ /g, ' ');
                  }}
                />
                <Tooltip
                  cursor={{ stroke: '#a1a1aa', strokeWidth: 1 }}
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const v = payload[0].value;
                    const formatted =
                      typeof v === 'number'
                        ? (formatSparkValue?.(v) ?? v.toLocaleString())
                        : String(v);
                    return (
                      <div className="rounded border bg-background px-2 py-1 text-xs shadow-sm">
                        <div className="text-muted-foreground">
                          {String(label).slice(0, 10)}
                        </div>
                        <div className="font-medium">{formatted}</div>
                      </div>
                    );
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke={SPARK_STROKE}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
