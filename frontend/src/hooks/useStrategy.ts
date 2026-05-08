import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

// ── Types ──────────────────────────────────────────────────────────

export interface MeResponse {
  user_id: number;
  name: string;
  can_use_strategy: boolean;
  can_view_top100: boolean;
  has_webhook: boolean;
}

export interface Strategy {
  id: number;
  user_id: number;
  name: string;
  direction: 'long' | 'short';
  contract: 'TX' | 'MTX' | 'TMF';
  contract_size: number;
  max_hold_days: number | null;
  entry_dsl: Record<string, unknown>;
  take_profit_dsl: Record<string, unknown>;
  stop_loss_dsl: Record<string, unknown>;
  notify_enabled: boolean;
  state: 'idle' | 'pending_entry' | 'open' | 'pending_exit';
  entry_signal_date: string | null;
  entry_fill_date: string | null;
  entry_fill_price: number | null;
  pending_exit_kind: string | null;
  pending_exit_signal_date: string | null;
  last_error: string | null;
  last_error_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SignalRecord {
  id: number;
  strategy_id: number;
  kind:
    | 'ENTRY_SIGNAL' | 'ENTRY_FILLED'
    | 'EXIT_SIGNAL'  | 'EXIT_FILLED'
    | 'MANUAL_RESET' | 'RUNTIME_ERROR';
  signal_date: string;
  close_at_signal: number | null;
  fill_price: number | null;
  exit_reason: string | null;
  pnl_points: number | null;
  pnl_amount: number | null;
  message: string | null;
  created_at: string;
}

export interface DslSchema {
  version: number;
  fields: string[];
  operators: string[];
  indicators: {
    name: string;
    params: {
      name: string;
      type: 'int' | 'float' | 'enum';
      min?: number;
      default?: number | string;
      choices?: string[];
    }[];
  }[];
  exit_modes: ('pct' | 'points' | 'dsl')[];
  vars: string[];
}

export interface StrategyCreatePayload {
  name: string;
  direction: 'long' | 'short';
  contract: 'TX' | 'MTX' | 'TMF';
  contract_size: number;
  max_hold_days?: number | null;
  entry_dsl: Record<string, unknown>;
  take_profit_dsl: Record<string, unknown>;
  stop_loss_dsl: Record<string, unknown>;
}

export interface StrategyUpdatePayload {
  name?: string;
  direction?: 'long' | 'short';
  contract?: 'TX' | 'MTX' | 'TMF';
  contract_size?: number;
  max_hold_days?: number | null;
  entry_dsl?: Record<string, unknown>;
  take_profit_dsl?: Record<string, unknown>;
  stop_loss_dsl?: Record<string, unknown>;
  notify_enabled?: boolean;
}

export interface BacktestRequestBody {
  start_date: string;
  end_date: string;
  contract?: 'TX' | 'MTX' | 'TMF';
  contract_size?: number;
}

export interface BacktestTrade {
  entry_date: string;
  entry_price: number;
  exit_date: string;
  exit_price: number;
  exit_reason: string;
  held_bars: number;
  pnl_points: number;
  pnl_amount: number;
  from_stop: boolean;
}

export interface BacktestSummary {
  total_pnl_amount: number;
  win_rate: number;
  avg_win_points: number;
  avg_loss_points: number;
  profit_factor: number;
  max_drawdown_amt: number;
  max_drawdown_pct: number;
  n_trades: number;
  avg_held_bars: number;
}

export interface BacktestResponse {
  trades: BacktestTrade[];
  summary: BacktestSummary;
  warnings: string[];
}

// ── Query hooks ────────────────────────────────────────────────────

export function useMe() {
  return useQuery<MeResponse>({
    queryKey: ['me'],
    queryFn: () => apiFetch<MeResponse>('/api/me'),
    staleTime: 60_000,
  });
}

export function useStrategies() {
  return useQuery<Strategy[]>({
    queryKey: ['strategies'],
    queryFn: () => apiFetch<Strategy[]>('/api/strategies'),
  });
}

export function useStrategy(id: number | undefined) {
  return useQuery<Strategy>({
    queryKey: ['strategy', id],
    queryFn: () => apiFetch<Strategy>(`/api/strategies/${id}`),
    enabled: id !== undefined && Number.isFinite(id),
  });
}

export function useStrategySignals(id: number | undefined, limit = 50) {
  return useQuery<SignalRecord[]>({
    queryKey: ['strategy', id, 'signals', limit],
    queryFn: () =>
      apiFetch<SignalRecord[]>(`/api/strategies/${id}/signals?limit=${limit}`),
    enabled: id !== undefined && Number.isFinite(id),
  });
}

export function useDslSchema() {
  return useQuery<DslSchema>({
    queryKey: ['dsl-schema'],
    queryFn: () => apiFetch<DslSchema>('/api/strategies/dsl/schema'),
    staleTime: Infinity,
  });
}

// ── Mutation hooks ────────────────────────────────────────────────

function invalidateOne(qc: ReturnType<typeof useQueryClient>, id: number) {
  qc.invalidateQueries({ queryKey: ['strategies'] });
  qc.invalidateQueries({ queryKey: ['strategy', id] });
  qc.invalidateQueries({ queryKey: ['strategy', id, 'signals'] });
}

export function useCreateStrategy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: StrategyCreatePayload) =>
      apiFetch<{ id: number }>('/api/strategies', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  });
}

export function useUpdateStrategy(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: StrategyUpdatePayload) =>
      apiFetch(`/api/strategies/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => invalidateOne(qc, id),
  });
}

export function useDeleteStrategy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/api/strategies/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  });
}

export function useEnableStrategy(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch(`/api/strategies/${id}/enable`, { method: 'POST' }),
    onSuccess: () => invalidateOne(qc, id),
  });
}

export function useDisableStrategy(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch(`/api/strategies/${id}/disable`, { method: 'POST' }),
    onSuccess: () => invalidateOne(qc, id),
  });
}

export function useForceCloseStrategy(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch(`/api/strategies/${id}/force_close`, { method: 'POST' }),
    onSuccess: () => invalidateOne(qc, id),
  });
}

export function useResetStrategy(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch(`/api/strategies/${id}/reset`, { method: 'POST' }),
    onSuccess: () => invalidateOne(qc, id),
  });
}

export function useBacktest(id: number) {
  return useMutation({
    mutationFn: (body: BacktestRequestBody) =>
      apiFetch<BacktestResponse>(`/api/strategies/${id}/backtest`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  });
}
