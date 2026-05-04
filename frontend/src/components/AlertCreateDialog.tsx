import { useState } from 'react';
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useWatchlist } from '@/hooks/useWatchlist';
import { useIndicatorsSpec } from '@/hooks/useIndicatorsSpec';
import { useCreateAlert, type CreateAlertPayload } from '@/hooks/useAlerts';
import { ApiError } from '@/lib/api-client';
import {
  INDICATOR_LABELS, STOCK_INDICATOR_LABELS, thresholdPlaceholder,
} from '@/lib/alert-labels';

type TargetType = 'indicator' | 'stock' | 'stock_indicator';

const ALL_CONDITIONS: ReadonlyArray<readonly [string, string]> = [
  ['above', '大於等於'],
  ['below', '小於等於'],
  ['streak_above', '連 N 日突破'],
  ['streak_below', '連 N 日跌破'],
  ['percentile_above', '5y 百分位突破'],
  ['percentile_below', '5y 百分位跌破'],
  ['yoy_above', 'YoY 突破'],
  ['yoy_below', 'YoY 跌破'],
];

interface Props {
  trigger: React.ReactNode;
}

export function AlertCreateDialog({ trigger }: Props) {
  const [open, setOpen] = useState(false);
  const [targetType, setTargetType] = useState<TargetType>('indicator');
  const [target, setTarget] = useState('');
  const [indicatorKey, setIndicatorKey] = useState('per');
  const [condition, setCondition] = useState('above');
  const [windowN, setWindowN] = useState('5');
  const [threshold, setThreshold] = useState('');

  const [error, setError] = useState<string | null>(null);
  const watchlist = useWatchlist();
  const spec = useIndicatorsSpec();
  const create = useCreateAlert();

  const submit = () => {
    setError(null);
    if (!target) {
      setError('請選擇目標');
      return;
    }
    if (threshold === '') {
      setError('請輸入門檻數值');
      return;
    }
    const payload: CreateAlertPayload = {
      target_type: targetType,
      target,
      condition,
      threshold: Number(threshold),
    };
    if (targetType === 'stock_indicator') payload.indicator_key = indicatorKey;
    if (condition.startsWith('streak_')) payload.window_n = Number(windowN);
    create.mutate(payload, {
      onSuccess: () => {
        setTarget('');
        setThreshold('');
        setOpen(false);
      },
      onError: (e: unknown) => {
        if (e instanceof ApiError) setError(e.message);
        else setError('建立失敗');
      },
    });
  };

  const indicatorOptions = Object.entries(INDICATOR_LABELS);
  const stockIndicatorOptions = Object.entries(STOCK_INDICATOR_LABELS);
  const tickerOptions = watchlist.data ?? [];

  function supportedConditions(): string[] {
    if (!spec.data) return ALL_CONDITIONS.map(([k]) => k);
    if (targetType === 'indicator' && target) {
      return (
        spec.data.indicator.find((s) => s.key === target)?.supported_conditions
        ?? ALL_CONDITIONS.map(([k]) => k)
      );
    }
    if (targetType === 'stock_indicator') {
      return (
        spec.data.stock_indicator.find((s) => s.key === indicatorKey)?.supported_conditions
        ?? ALL_CONDITIONS.map(([k]) => k)
      );
    }
    return ALL_CONDITIONS.map(([k]) => k);
  }
  const allowed = supportedConditions();
  const conditionOptions = ALL_CONDITIONS.filter(([k]) => allowed.includes(k));

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新增價格警示</DialogTitle>
          <DialogDescription>達到門檻時將推送 Discord 通知。</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <div>
            <label className="text-sm font-medium block mb-1">類型</label>
            <Select
              value={targetType}
              onValueChange={(v) => {
                setTargetType(v as TargetType);
                setTarget('');
              }}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="indicator">指標</SelectItem>
                <SelectItem value="stock">股票 / ETF</SelectItem>
                <SelectItem value="stock_indicator">個股指標</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <label className="text-sm font-medium block mb-1">目標</label>
            <Select value={target} onValueChange={setTarget}>
              <SelectTrigger><SelectValue placeholder="選擇" /></SelectTrigger>
              <SelectContent>
                {targetType === 'indicator' && indicatorOptions.map(([k, label]) => (
                  <SelectItem key={k} value={k}>{label}</SelectItem>
                ))}
                {targetType !== 'indicator' && tickerOptions.length === 0 && (
                  <SelectItem value="__none__" disabled>（請先在自選股新增）</SelectItem>
                )}
                {targetType !== 'indicator' && tickerOptions.map((s) => (
                  <SelectItem key={s.ticker} value={s.ticker}>
                    {s.name ? `${s.ticker} · ${s.name}` : s.ticker}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {targetType === 'stock_indicator' && (
            <div>
              <label className="text-sm font-medium block mb-1">個股指標</label>
              <Select value={indicatorKey} onValueChange={setIndicatorKey}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {stockIndicatorOptions.map(([k, label]) => (
                    <SelectItem key={k} value={k}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div>
            <label className="text-sm font-medium block mb-1">條件</label>
            <Select value={condition} onValueChange={setCondition}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {conditionOptions.map(([k, label]) => (
                  <SelectItem key={k} value={k}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {condition.startsWith('streak_') && (
            <div>
              <label htmlFor="alert-window-n" className="text-sm font-medium block mb-1">N 日</label>
              <Input
                id="alert-window-n"
                type="number" min={2} max={30}
                value={windowN}
                onChange={(e) => setWindowN(e.target.value)}
              />
            </div>
          )}

          <div>
            <label htmlFor="alert-threshold" className="text-sm font-medium block mb-1">門檻</label>
            <Input
              id="alert-threshold"
              type="number" step="any"
              placeholder={thresholdPlaceholder(condition)}
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
            />
          </div>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => setOpen(false)} disabled={create.isPending}>
            取消
          </Button>
          <Button onClick={submit} disabled={create.isPending}>
            {create.isPending ? '建立中…' : '建立'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
