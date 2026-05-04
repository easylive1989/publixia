import { X } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { AlertCreateDialog } from '@/components/AlertCreateDialog';
import { useAlerts, useDeleteAlert, useToggleAlert } from '@/hooks/useAlerts';
import { alertTargetLabel, conditionLabel } from '@/lib/alert-labels';
import { cn } from '@/lib/utils';
import { registerCard } from './registry';

function fmtThreshold(v: number | null): string {
  if (v == null) return '';
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function StatusBadge({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={cn(
        'rounded px-2 py-0.5 text-xs font-medium',
        enabled
          ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200'
          : 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200',
      )}
    >
      {enabled ? '監控中' : '已停用'}
    </span>
  );
}

function AlertsCard() {
  const { data, isLoading, isError } = useAlerts();
  const toggle = useToggleAlert();
  const del = useDeleteAlert();

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>價格警示</CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            觸發後自動停用，可手動重新啟用
          </p>
        </div>
        <AlertCreateDialog trigger={<Button size="sm">+ 新增警示</Button>} />
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
        {isError && <p className="text-sm text-destructive">無法載入</p>}
        {data && data.length === 0 && (
          <p className="text-sm text-muted-foreground py-2 text-center">
            尚未設定任何警示
          </p>
        )}
        {data && data.length > 0 && (
          <ul className="divide-y">
            {data.map((a) => {
              const enabled = a.enabled === 1 || a.enabled === true;
              const meta =
                `建立於 ${a.created_at?.slice(0, 10) ?? ''}`
                + (a.triggered_at
                  ? ` · 已於 ${a.triggered_at.slice(0, 10)} 觸發 (${fmtThreshold(a.triggered_value)})`
                  : '');
              return (
                <li
                  key={a.id}
                  className="py-2 flex items-center justify-between gap-3"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm">
                      <strong>{alertTargetLabel(a)}</strong>{' '}
                      {conditionLabel(a)}{' '}
                      <strong>{fmtThreshold(a.threshold)}</strong>{' '}
                      <StatusBadge enabled={enabled} />
                    </div>
                    <div className="text-xs text-muted-foreground">{meta}</div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => toggle.mutate({ id: a.id, enabled: !enabled })}
                      disabled={toggle.isPending && toggle.variables?.id === a.id}
                    >
                      {enabled ? '停用' : '啟用'}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => del.mutate(a.id)}
                      disabled={del.isPending && del.variables === a.id}
                      aria-label={`刪除警示 ${a.id}`}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'alerts',
  label: '價格警示',
  defaultPage: 'dashboard',
  component: AlertsCard,
  cols: 3,
});
