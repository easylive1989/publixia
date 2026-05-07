import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import type { Strategy } from '@/hooks/useStrategy';

const STATE_LABELS: Record<Strategy['state'], string> = {
  idle:          '待機',
  pending_entry: '待進場 (明日 open 假想成交)',
  open:          '在場內',
  pending_exit:  '待出場 (明日 open 假想結算)',
};

interface Props {
  strategy: Strategy;
  onForceClose?: () => void;
  onReset?: () => void;
}

export function PositionStatusCard({ strategy, onForceClose, onReset }: Props) {
  const inPosition = strategy.state === 'open' || strategy.state === 'pending_exit';
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">持倉狀態</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div>
          <span className="text-muted-foreground">狀態:</span>{' '}
          {STATE_LABELS[strategy.state]}
        </div>
        {strategy.entry_signal_date && (
          <div>
            <span className="text-muted-foreground">進場訊號日:</span>{' '}
            {strategy.entry_signal_date}
          </div>
        )}
        {strategy.entry_fill_price !== null && (
          <div>
            <span className="text-muted-foreground">進場價 / 進場日:</span>{' '}
            {strategy.entry_fill_price.toLocaleString()} @ {strategy.entry_fill_date}
          </div>
        )}
        {strategy.pending_exit_kind && (
          <div>
            <span className="text-muted-foreground">出場類型:</span>{' '}
            {strategy.pending_exit_kind}
          </div>
        )}
        {strategy.last_error && (
          <div className="text-destructive">
            <span className="font-medium">最近錯誤:</span>{' '}
            {strategy.last_error}
          </div>
        )}
        <div className="flex gap-2 pt-2">
          {inPosition && onForceClose && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                if (window.confirm('確認用最新 close 強制平倉?')) onForceClose();
              }}
            >
              強制平倉
            </Button>
          )}
          {onReset && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                if (window.confirm(
                  '確認重置策略?所有訊號歷史會被刪除、狀態回到待機。',
                )) onReset();
              }}
            >
              重置
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
