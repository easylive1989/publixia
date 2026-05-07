import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  useStrategy, useStrategySignals, useDslSchema,
  useCreateStrategy, useUpdateStrategy,
  useEnableStrategy, useDisableStrategy,
  useForceCloseStrategy, useResetStrategy, useMe,
  type StrategyCreatePayload, type StrategyUpdatePayload,
} from '@/hooks/useStrategy';
import { ApiError } from '@/lib/api-client';
import { StrategyForm } from '@/components/strategy/StrategyForm';
import { PositionStatusCard } from '@/components/strategy/PositionStatusCard';
import { SignalHistoryTable } from '@/components/strategy/SignalHistoryTable';
import { BacktestPanel } from '@/components/strategy/BacktestPanel';
import type { DslCondition } from '@/components/strategy/ConditionRow';
import type { ExitDsl } from '@/components/strategy/ExitConditionEditor';
import { useState } from 'react';

export default function StrategyEditPage() {
  const params = useParams<{ id?: string }>();
  const id = params.id ? Number(params.id) : undefined;
  const isEdit = id !== undefined && Number.isFinite(id);

  const navigate = useNavigate();
  const { data: me } = useMe();
  const { data: schema } = useDslSchema();
  const { data: strategy, error: loadError } = useStrategy(id);
  const { data: signals } = useStrategySignals(id);

  const create = useCreateStrategy();
  const update = useUpdateStrategy(id ?? 0);
  const enable = useEnableStrategy(id ?? 0);
  const disable = useDisableStrategy(id ?? 0);
  const forceClose = useForceCloseStrategy(id ?? 0);
  const reset = useResetStrategy(id ?? 0);
  const [serverError, setServerError] = useState<string | null>(null);

  if (!schema) return <div className="p-8 text-muted-foreground">載入中…</div>;
  if (isEdit && loadError) {
    return <div className="p-8 text-destructive">載入失敗:{(loadError as Error).message}</div>;
  }
  if (isEdit && !strategy) {
    return <div className="p-8 text-muted-foreground">載入中…</div>;
  }

  const handleSubmit = (payload: StrategyCreatePayload | StrategyUpdatePayload) => {
    setServerError(null);
    if (isEdit) {
      update.mutate(payload as StrategyUpdatePayload, {
        onError: (e: unknown) => setServerError(e instanceof ApiError ? e.message : '儲存失敗'),
      });
    } else {
      create.mutate(payload as StrategyCreatePayload, {
        onSuccess: ({ id: newId }) => navigate(`/strategies/${newId}`),
        onError: (e: unknown) => setServerError(e instanceof ApiError ? e.message : '建立失敗'),
      });
    }
  };

  return (
    <div className="container mx-auto p-4 space-y-4 max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">
          {isEdit ? `策略:${strategy?.name}` : '建立策略'}
        </h1>
        <Button variant="outline" onClick={() => navigate('/strategies')}>
          返回列表
        </Button>
      </div>

      {isEdit && strategy && (
        <PositionStatusCard
          strategy={strategy}
          onForceClose={() => forceClose.mutate()}
          onReset={() => reset.mutate()}
        />
      )}

      {isEdit && strategy && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">即時通知</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>
              狀態:{strategy.notify_enabled ? '已啟用' : '停用'}
              {!me?.has_webhook && (
                <span className="text-amber-700 ml-2">
                  (尚未設定 Discord webhook,請聯繫 admin)
                </span>
              )}
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={strategy.notify_enabled || !me?.has_webhook}
                onClick={() => enable.mutate()}
              >
                啟用
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={!strategy.notify_enabled}
                onClick={() => disable.mutate()}
              >
                停用
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {isEdit ? '編輯條件' : '條件設定'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <StrategyForm
            schema={schema}
            mode={isEdit ? 'edit' : 'create'}
            initial={
              strategy
                ? {
                    name: strategy.name,
                    direction: strategy.direction,
                    contract: strategy.contract,
                    contract_size: strategy.contract_size,
                    max_hold_days: strategy.max_hold_days,
                    entry_dsl: strategy.entry_dsl as { version: 1; all: DslCondition[] },
                    take_profit_dsl: strategy.take_profit_dsl as ExitDsl,
                    stop_loss_dsl: strategy.stop_loss_dsl as ExitDsl,
                    state: strategy.state,
                  }
                : undefined
            }
            onSubmit={handleSubmit}
            saving={create.isPending || update.isPending}
            serverError={serverError}
          />
        </CardContent>
      </Card>

      {isEdit && signals && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">訊號歷史</CardTitle>
          </CardHeader>
          <CardContent>
            <SignalHistoryTable signals={signals} />
          </CardContent>
        </Card>
      )}

      {isEdit && id !== undefined && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">回測</CardTitle>
          </CardHeader>
          <CardContent>
            <BacktestPanel strategyId={id} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
