import { useEffect, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useRefreshForeignFutures } from '@/hooks/useForeignFutures';
import { ApiError } from '@/lib/api-client';

interface RefreshDataButtonProps {
  disabled?: boolean;
}

const FETCHER_LABEL: Record<string, string> = {
  tw_futures:    '台指期日線',
  inst_futures:  '外資台指/小台未平倉',
  inst_options:  '三大法人 TXO',
  large_trader:  '大額交易人 (散戶比)',
  txo_strike_oi: 'TXO 各履約價 OI',
};

export function RefreshDataButton({ disabled }: RefreshDataButtonProps) {
  const refresh = useRefreshForeignFutures();
  const [message, setMessage] = useState<string | null>(null);
  const [tone, setTone] = useState<'ok' | 'warn' | 'error'>('ok');

  // Auto-dismiss success/warning banners; keep errors until next click.
  useEffect(() => {
    if (!message || tone === 'error') return;
    const t = setTimeout(() => setMessage(null), 6000);
    return () => clearTimeout(t);
  }, [message, tone]);

  function handleClick() {
    setMessage(null);
    refresh.mutate(undefined, {
      onSuccess: (resp) => {
        if (resp.ok) {
          setTone('ok');
          setMessage('資料已更新');
        } else {
          const failed = Object.entries(resp.results)
            .filter(([, r]) => r.status === 'error')
            .map(([k]) => FETCHER_LABEL[k] ?? k);
          setTone('warn');
          setMessage(`部分資料更新失敗: ${failed.join('、')}`);
        }
      },
      onError: (err) => {
        setTone('error');
        if (err instanceof ApiError && err.status === 409) {
          setMessage('已有另一個更新作業進行中,請稍後再試');
        } else {
          setMessage(`更新失敗: ${err.message}`);
        }
      },
    });
  }

  const isPending = refresh.isPending;
  const isDisabled = disabled || isPending;

  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={isDisabled}
        onClick={handleClick}
        aria-label="主動更新外資期貨動向資料"
        className="gap-1"
      >
        {isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <RefreshCw className="h-4 w-4" />
        )}
        {isPending ? '更新中…' : '更新資料'}
      </Button>
      {isPending && (
        <p className="text-xs text-muted-foreground">
          正在重新抓取 TAIFEX 資料,約需 30–60 秒
        </p>
      )}
      {message && !isPending && (
        <p
          className={
            tone === 'error'
              ? 'text-xs text-destructive'
              : tone === 'warn'
                ? 'text-xs text-amber-600 dark:text-amber-400'
                : 'text-xs text-muted-foreground'
          }
        >
          {message}
        </p>
      )}
    </div>
  );
}
