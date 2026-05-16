import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useDashboardData } from '@/hooks/useDashboardData';
import { registerCard } from './registry';

// Same shape as dashboard-cards.tsx — keep the formatter local so the two
// files don't have to share a private helper.
function fmtNextUpdate(iso: string | null | undefined): string {
  if (!iso) return '';
  const m = iso.match(/^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return '';
  const [, mm, dd, hh, mi] = m;
  return `${mm}-${dd} ${hh}:${mi}`;
}

function MarginBalanceCard() {
  const { data, isLoading, isError } = useDashboardData();

  const margin = data?.margin_balance;
  const short  = data?.short_balance;
  const ratio  = data?.short_margin_ratio;
  const nextUpdate = fmtNextUpdate(margin?.next_update_at);

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          融資 / 融券餘額
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
        {isError   && <p className="text-sm text-destructive">無法載入</p>}
        {!isLoading && !isError && (
          <>
            <table className="w-full">
              <tbody>
                <tr className="border-b last:border-0">
                  <td className="py-2 text-sm text-muted-foreground">融資餘額</td>
                  <td className="py-2 text-right text-lg font-semibold tabular-nums">
                    {margin ? `${margin.value.toLocaleString()} 億` : '—'}
                  </td>
                </tr>
                <tr>
                  <td className="py-2 text-sm text-muted-foreground">融券餘額</td>
                  <td className="py-2 text-right text-lg font-semibold tabular-nums">
                    {short ? `${(short.value / 1000).toFixed(0)} 千張` : '—'}
                  </td>
                </tr>
              </tbody>
            </table>
            <div className="space-y-0.5 text-xs text-muted-foreground">
              <p>券資比 {ratio ? `${ratio.value.toFixed(2)} %` : '—'}</p>
              {nextUpdate && <p>下次更新 {nextUpdate}</p>}
            </div>
          </>
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
