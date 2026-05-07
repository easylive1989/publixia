import { Link } from 'react-router-dom';
import { useStrategies, useDeleteStrategy, type Strategy } from '@/hooks/useStrategy';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Plus, Trash2 } from 'lucide-react';

const STATE_LABELS: Record<Strategy['state'], string> = {
  idle:           '待機',
  pending_entry:  '待進場',
  open:           '在場內',
  pending_exit:   '待出場',
};

const STATE_COLOURS: Record<Strategy['state'], string> = {
  idle:           'bg-muted text-muted-foreground',
  pending_entry:  'bg-amber-500/15 text-amber-700',
  open:           'bg-emerald-500/15 text-emerald-700',
  pending_exit:   'bg-orange-500/15 text-orange-700',
};

export default function StrategiesListPage() {
  const { data, isLoading, error } = useStrategies();
  const del = useDeleteStrategy();

  const handleDelete = (id: number, name: string) => {
    if (window.confirm(`確認刪除策略 "${name}" 與其所有訊號歷史?`)) {
      del.mutate(id);
    }
  };

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">策略列表</h1>
        <Button asChild>
          <Link to="/strategies/new">
            <Plus className="h-4 w-4 mr-1" />
            建立策略
          </Link>
        </Button>
      </div>

      {isLoading && <p className="text-muted-foreground">載入中…</p>}
      {error && (
        <p className="text-destructive">載入失敗:{(error as Error).message}</p>
      )}

      {data?.length === 0 && (
        <Card>
          <CardContent className="p-8 text-center text-muted-foreground">
            還沒有策略。點右上角「建立策略」開始。
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {data?.map((s) => (
          <Card key={s.id}>
            <CardHeader className="flex flex-row items-start justify-between gap-2">
              <CardTitle className="text-base">
                <Link to={`/strategies/${s.id}`} className="hover:underline">
                  {s.name}
                </Link>
              </CardTitle>
              <span
                className={`text-xs px-2 py-1 rounded ${STATE_COLOURS[s.state]}`}
              >
                {STATE_LABELS[s.state]}
              </span>
            </CardHeader>
            <CardContent className="text-sm space-y-1">
              <div className="text-muted-foreground">
                {s.direction === 'long' ? '多' : '空'} · {s.contract} · {s.contract_size} 口
              </div>
              <div className="text-muted-foreground">
                即時通知:{s.notify_enabled ? '✓ 已啟用' : '✗ 停用'}
              </div>
              {s.last_error && (
                <div className="text-destructive text-xs">
                  錯誤:{s.last_error.slice(0, 60)}…
                </div>
              )}
            </CardContent>
            <CardFooter className="flex justify-end gap-2">
              <Button
                size="sm"
                variant="ghost"
                aria-label={`刪除 ${s.name}`}
                onClick={() => handleDelete(s.id, s.name)}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </CardFooter>
          </Card>
        ))}
      </div>
    </div>
  );
}
