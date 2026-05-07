# FSE Phase 5 — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React UI under `/strategies` so a permitted user can list / create / edit / enable-disable / force-close / reset / backtest strategies through the browser. Read-only access shows position state + signal history; the condition builder lets users compose entry / take-profit / stop-loss DSLs without writing JSON; the backtest panel renders trades + summary + a Recharts equity curve.

**Architecture:** New TanStack-Query hooks under `src/hooks/useStrategy.ts` wrap the P4 endpoints; new React-Router routes under `/strategies`, `/strategies/new`, `/strategies/:id` mounted in `src/router.tsx`. UI components in `src/components/strategy/` follow the existing project's Radix + shadcn-flavoured patterns. Permission gating is purely frontend (`useMe.can_use_strategy`) — backend already enforces 403 in P4. Tests use `vitest + @testing-library/react + msw` mirroring the project's existing pattern (e.g. `tests/useDashboardData.test.tsx`, `tests/AlertCreateDialog.test.tsx`).

**Tech Stack:** React 18 / Vite / TypeScript / TanStack Query 5 / Zustand / Radix UI primitives / Tailwind / Recharts 3 / vitest + @testing-library/react + msw.

**Spec reference:** `docs/superpowers/specs/2026-05-05-futures-strategy-engine-design.md` §9 (frontend organisation).

---

## File Structure

**Created (frontend src):**
- `src/hooks/useStrategy.ts` — types + TanStack Query hooks: `useMe`, `useStrategies`, `useStrategy(id)`, `useStrategySignals(id)`, `useDslSchema`, plus the eight mutations (`useCreateStrategy`, `useUpdateStrategy`, `useDeleteStrategy`, `useEnableStrategy`, `useDisableStrategy`, `useForceCloseStrategy`, `useResetStrategy`, `useBacktest`).
- `src/components/strategy/NavLink.tsx` — header link rendered only when `me.can_use_strategy`.
- `src/components/strategy/PermissionGate.tsx` — wraps `/strategies/*` route content; shows `<NotAuthorized/>` on `can_use_strategy=false`.
- `src/components/strategy/ExpressionPicker.tsx` — picks `{field}` / `{indicator,...}` / `{const}` / `{var}`.
- `src/components/strategy/OperatorSelect.tsx` — 8 operators dropdown.
- `src/components/strategy/ConditionRow.tsx` — single `<expr> <op> <expr>` line with optional `n` for streak.
- `src/components/strategy/ConditionBuilder.tsx` — list of ConditionRow + add/remove buttons.
- `src/components/strategy/ExitConditionEditor.tsx` — toggle pct / points / advanced; advanced delegates to ConditionBuilder.
- `src/components/strategy/StrategyForm.tsx` — full create/edit form combining the builder + metadata fields.
- `src/components/strategy/PositionStatusCard.tsx` — renders `state`, entry price, last error.
- `src/components/strategy/SignalHistoryTable.tsx` — last N signal rows.
- `src/components/strategy/BacktestPanel.tsx` — date-range form + run + summary cards + trades table + equity curve chart.
- `src/components/strategy/EquityCurveChart.tsx` — Recharts line chart of cumulative pnl_amount over trade exit dates.
- `src/pages/StrategiesListPage.tsx`
- `src/pages/StrategyEditPage.tsx`
- `tests/useStrategy.test.tsx`
- `tests/strategy/ConditionBuilder.test.tsx`
- `tests/strategy/ExitConditionEditor.test.tsx`
- `tests/strategy/StrategyForm.test.tsx`
- `tests/strategy/BacktestPanel.test.tsx`
- `tests/strategy/StrategiesListPage.test.tsx`

**Modified:**
- `src/router.tsx` — register the three new routes.
- `src/pages/DashboardPage.tsx` — add the "策略" link in the header next to the existing settings dialog (rendered conditionally via `<NavLink/>` from this task's Plumbing).

**Out of scope (deferred):**
- Per-signal embed preview (the actual Discord embed image renders server-side at posting time).
- Frontend-driven backfill of futures_daily for backtest ranges that have no bars (P6 — the user can simply pick a tighter range).
- Equity curve benchmark overlay (Buy-and-Hold) — backend always sends an empty list right now (P2 deferred). Frontend renders only the strategy's curve. Re-introduce when P2.5 populates `BacktestResult.benchmark`.

---

## Task 1 — API hooks + permission gating

**Files:**
- Create: `frontend/src/hooks/useStrategy.ts`
- Create: `frontend/src/components/strategy/NavLink.tsx`
- Create: `frontend/src/components/strategy/PermissionGate.tsx`
- Create: `frontend/tests/useStrategy.test.tsx`
- Modify: `frontend/src/router.tsx`

This task lays the data + routing groundwork. Pages added in Task 3 + 4 + 5 will mount under the routes registered here.

- [ ] **Step 1.1: Write the failing hook tests**

Create `frontend/tests/useStrategy.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import { useMe, useStrategies, useDslSchema } from '../src/hooks/useStrategy';

function wrapper(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

const queryClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false } } });

describe('useMe', () => {
  it('returns identity + can_use_strategy + has_webhook', async () => {
    server.use(
      http.get('*/api/me', () =>
        HttpResponse.json({
          user_id: 1, name: 'paul',
          can_use_strategy: true, has_webhook: false,
        }),
      ),
    );
    const { result } = renderHook(() => useMe(), { wrapper: wrapper(queryClient()) });
    await waitFor(() => expect(result.current.data?.name).toBe('paul'));
    expect(result.current.data?.can_use_strategy).toBe(true);
    expect(result.current.data?.has_webhook).toBe(false);
  });
});

describe('useStrategies', () => {
  it('returns the user list', async () => {
    server.use(
      http.get('*/api/strategies', () =>
        HttpResponse.json([
          { id: 1, name: 'rsi_long', state: 'idle', notify_enabled: false },
        ]),
      ),
    );
    const { result } = renderHook(() => useStrategies(), { wrapper: wrapper(queryClient()) });
    await waitFor(() => expect(result.current.data?.length).toBe(1));
    expect(result.current.data?.[0].name).toBe('rsi_long');
  });
});

describe('useDslSchema', () => {
  it('exposes fields / operators / indicators', async () => {
    server.use(
      http.get('*/api/strategies/dsl/schema', () =>
        HttpResponse.json({
          version: 1,
          fields: ['close'],
          operators: ['gt'],
          indicators: [{ name: 'sma', params: [{ name: 'n', type: 'int', min: 1 }] }],
          exit_modes: ['pct', 'points', 'dsl'],
          vars: ['entry_price'],
        }),
      ),
    );
    const { result } = renderHook(() => useDslSchema(), { wrapper: wrapper(queryClient()) });
    await waitFor(() => expect(result.current.data?.indicators[0].name).toBe('sma'));
  });
});
```

- [ ] **Step 1.2: Run — should fail**

```bash
cd /Users/paulwu/Documents/Github/publixia/frontend
npm test -- useStrategy 2>&1 | tail -20
```

Expected: import error for `../src/hooks/useStrategy`.

- [ ] **Step 1.3: Implement the hooks file**

Create `frontend/src/hooks/useStrategy.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

// ── Types ──────────────────────────────────────────────────────────

export interface MeResponse {
  user_id: number;
  name: string;
  can_use_strategy: boolean;
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
```

- [ ] **Step 1.4: Implement permission gate + nav link**

Create `frontend/src/components/strategy/PermissionGate.tsx`:

```tsx
import { type ReactNode } from 'react';
import { useMe } from '@/hooks/useStrategy';

export function PermissionGate({ children }: { children: ReactNode }) {
  const { data: me, isLoading } = useMe();
  if (isLoading) {
    return (
      <div className="container mx-auto p-8 text-muted-foreground">
        正在驗證權限…
      </div>
    );
  }
  if (!me?.can_use_strategy) {
    return (
      <div className="container mx-auto p-8 max-w-xl">
        <h1 className="text-2xl font-bold mb-2">沒有策略系統權限</h1>
        <p className="text-muted-foreground">
          此功能僅開放給有權限的使用者。請聯繫 admin 開通。
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
```

Create `frontend/src/components/strategy/NavLink.tsx`:

```tsx
import { Link } from 'react-router-dom';
import { useMe } from '@/hooks/useStrategy';

export function StrategiesNavLink() {
  const { data: me } = useMe();
  if (!me?.can_use_strategy) return null;
  return (
    <Link
      to="/strategies"
      className="text-sm font-medium hover:underline text-muted-foreground"
    >
      策略
    </Link>
  );
}
```

- [ ] **Step 1.5: Register the routes**

Edit `frontend/src/router.tsx`:

Replace its full content with:

```tsx
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import DashboardPage from './pages/DashboardPage';
import StockDetailPage from './pages/StockDetailPage';
import FuturesDetailPage from './pages/FuturesDetailPage';
import { PermissionGate } from './components/strategy/PermissionGate';

const StrategiesListPage = lazy(() => import('./pages/StrategiesListPage'));
const StrategyEditPage   = lazy(() => import('./pages/StrategyEditPage'));

function gated(node: React.ReactNode) {
  return (
    <PermissionGate>
      <Suspense fallback={<div className="p-8 text-muted-foreground">載入中…</div>}>
        {node}
      </Suspense>
    </PermissionGate>
  );
}

export function createRouter() {
  return createBrowserRouter([
    { path: '/', element: <DashboardPage /> },
    { path: '/stock/:code', element: <StockDetailPage /> },
    { path: '/futures/tw', element: <FuturesDetailPage /> },
    { path: '/strategies',         element: gated(<StrategiesListPage />) },
    { path: '/strategies/new',     element: gated(<StrategyEditPage />) },
    { path: '/strategies/:id',     element: gated(<StrategyEditPage />) },
    { path: '*', element: <Navigate to="/" replace /> },
  ]);
}
```

The lazy imports will fail until Tasks 3 + 4 land; that's expected. Vite + Suspense will only try to load them when navigating to those paths.

- [ ] **Step 1.6: Run hook tests — should pass**

```bash
cd /Users/paulwu/Documents/Github/publixia/frontend
npm test -- useStrategy 2>&1 | tail -15
```

Expected: 3 tests PASS.

- [ ] **Step 1.7: Run full frontend test suite to confirm no regression**

```bash
cd /Users/paulwu/Documents/Github/publixia/frontend
npm test 2>&1 | tail -10
```

Expected: pre-existing tests still pass; total +3.

- [ ] **Step 1.8: Confirm dev build still compiles**

```bash
cd /Users/paulwu/Documents/Github/publixia/frontend
npm run build 2>&1 | tail -5
```

Expected: `vite build` succeeds without TypeScript errors. The lazy imports for the not-yet-existing pages will be flagged — if `npm run build` errors out, temporarily replace the lazy imports with stub components like `const StrategiesListPage = () => <div>placeholder</div>;` and revert when Task 3 lands. **If you take the stub workaround, file a TODO at the top of `router.tsx` so a later task removes the stubs.** A cleaner approach is to land minimal placeholder page files in this commit:

```tsx
// src/pages/StrategiesListPage.tsx
export default function StrategiesListPage() {
  return <div className="p-8 text-muted-foreground">List page coming soon…</div>;
}
// src/pages/StrategyEditPage.tsx
export default function StrategyEditPage() {
  return <div className="p-8 text-muted-foreground">Edit page coming soon…</div>;
}
```

Use the placeholder approach — Task 3 + 4 replace the file contents.

- [ ] **Step 1.9: Commit**

```bash
cd /Users/paulwu/Documents/Github/publixia
git add frontend/src/hooks/useStrategy.ts \
        frontend/src/components/strategy/NavLink.tsx \
        frontend/src/components/strategy/PermissionGate.tsx \
        frontend/src/router.tsx \
        frontend/src/pages/StrategiesListPage.tsx \
        frontend/src/pages/StrategyEditPage.tsx \
        frontend/tests/useStrategy.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): strategy hooks + routing scaffold

useStrategy.ts exposes typed TanStack Query hooks for every P4
endpoint: useMe, useStrategies, useStrategy, useStrategySignals,
useDslSchema, plus mutations for create/update/delete/enable/
disable/force_close/reset/backtest.

Router gains /strategies, /strategies/new, /strategies/:id under a
PermissionGate that reads useMe.can_use_strategy and falls back to
a "no permission" view for users without the flag. Pages are loaded
lazily so route bundles stay split.

Pages are placeholders for now; Tasks 3 + 4 land the real content.
EOF
)"
```

Do NOT amend, do NOT push.

---

## Task 2 — DSL builder components

**Files:**
- Create: `frontend/src/components/strategy/ExpressionPicker.tsx`
- Create: `frontend/src/components/strategy/OperatorSelect.tsx`
- Create: `frontend/src/components/strategy/ConditionRow.tsx`
- Create: `frontend/src/components/strategy/ConditionBuilder.tsx`
- Create: `frontend/src/components/strategy/ExitConditionEditor.tsx`
- Create: `frontend/tests/strategy/ConditionBuilder.test.tsx`
- Create: `frontend/tests/strategy/ExitConditionEditor.test.tsx`

These four atomic components are the DSL UI. They take typed values + onChange callbacks; no external state, no API calls. The Edit page in Task 4 owns the DSL JSON state and passes it down.

- [ ] **Step 2.1: Write the failing builder tests**

Create `frontend/tests/strategy/ConditionBuilder.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConditionBuilder } from '../../src/components/strategy/ConditionBuilder';
import type { DslSchema } from '../../src/hooks/useStrategy';

const SCHEMA: DslSchema = {
  version: 1,
  fields: ['close', 'high', 'low'],
  operators: ['gt', 'lt', 'cross_above', 'streak_above'],
  indicators: [
    { name: 'sma', params: [{ name: 'n', type: 'int', min: 1 }] },
  ],
  exit_modes: ['pct', 'points', 'dsl'],
  vars: ['entry_price'],
};

describe('ConditionBuilder', () => {
  it('renders an empty list with an "add condition" button when value is empty', () => {
    render(
      <ConditionBuilder schema={SCHEMA} value={[]} onChange={() => {}} />,
    );
    expect(screen.getByRole('button', { name: /新增條件/ })).toBeInTheDocument();
  });

  it('emits a default condition when "新增條件" is clicked', () => {
    const calls: unknown[] = [];
    render(
      <ConditionBuilder
        schema={SCHEMA}
        value={[]}
        onChange={(v) => calls.push(v)}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /新增條件/ }));
    expect(calls).toHaveLength(1);
    const newList = calls[0] as Array<{ left: unknown; op: string; right: unknown }>;
    expect(newList.length).toBe(1);
    expect(newList[0].op).toBe('gt');
  });

  it('removes a row when its delete button is clicked', () => {
    const initial = [
      {
        left: { field: 'close' as const },
        op: 'gt' as const,
        right: { const: 100 },
      },
    ];
    const calls: unknown[][] = [];
    render(
      <ConditionBuilder
        schema={SCHEMA}
        value={initial}
        onChange={(v) => calls.push(v)}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /刪除條件/ }));
    expect(calls[0]).toHaveLength(0);
  });

  it('hides entry_price from the var dropdown when allowEntryPrice is false', () => {
    render(
      <ConditionBuilder
        schema={SCHEMA}
        value={[
          {
            left: { field: 'close' as const },
            op: 'gt' as const,
            right: { const: 100 },
          },
        ]}
        onChange={() => {}}
        allowEntryPrice={false}
      />,
    );
    // The "Var" expression-type option should not appear when entry_price is disallowed.
    const buttons = screen.queryAllByRole('option', { name: /進場價/ });
    expect(buttons).toHaveLength(0);
  });
});
```

Create `frontend/tests/strategy/ExitConditionEditor.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ExitConditionEditor } from '../../src/components/strategy/ExitConditionEditor';
import type { DslSchema } from '../../src/hooks/useStrategy';

const SCHEMA: DslSchema = {
  version: 1,
  fields: ['close'],
  operators: ['gt', 'lt'],
  indicators: [],
  exit_modes: ['pct', 'points', 'dsl'],
  vars: ['entry_price'],
};

describe('ExitConditionEditor', () => {
  it('starts in pct mode and emits {type:pct,value} on change', () => {
    const calls: unknown[] = [];
    render(
      <ExitConditionEditor
        schema={SCHEMA}
        value={{ version: 1, type: 'pct', value: 2.0 }}
        onChange={(v) => calls.push(v)}
      />,
    );
    const input = screen.getByLabelText(/百分比/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '3.5' } });
    expect(calls.at(-1)).toMatchObject({ type: 'pct', value: 3.5 });
  });

  it('switches to points mode and resets value', () => {
    const calls: unknown[] = [];
    render(
      <ExitConditionEditor
        schema={SCHEMA}
        value={{ version: 1, type: 'pct', value: 2.0 }}
        onChange={(v) => calls.push(v)}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /^點數$/ }));
    expect(calls.at(-1)).toMatchObject({ type: 'points' });
  });

  it('switches to advanced (dsl) mode and shows the ConditionBuilder', () => {
    render(
      <ExitConditionEditor
        schema={SCHEMA}
        value={{ version: 1, type: 'pct', value: 2.0 }}
        onChange={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /進階/ }));
    // Advanced mode renders the condition builder with entry_price available.
    expect(screen.getByRole('button', { name: /新增條件/ })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2.2: Run — should fail**

```bash
cd /Users/paulwu/Documents/Github/publixia/frontend
npm test -- strategy/ConditionBuilder 2>&1 | tail -15
```

Expected: import error.

- [ ] **Step 2.3: Implement the atomic pickers**

Create `frontend/src/components/strategy/OperatorSelect.tsx`:

```tsx
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';

const OP_LABELS: Record<string, string> = {
  gt: '>', gte: '>=', lt: '<', lte: '<=',
  cross_above: '上穿', cross_below: '下穿',
  streak_above: '連 N 日 ≥', streak_below: '連 N 日 ≤',
};

interface Props {
  value: string;
  onChange: (v: string) => void;
  operators: string[];
}

export function OperatorSelect({ value, onChange, operators }: Props) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-32" aria-label="運算子">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {operators.map((op) => (
          <SelectItem key={op} value={op}>
            {OP_LABELS[op] ?? op}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
```

Create `frontend/src/components/strategy/ExpressionPicker.tsx`:

```tsx
import { useMemo } from 'react';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import type { DslSchema } from '@/hooks/useStrategy';

export type Expression =
  | { field: string }
  | { indicator: string; [key: string]: unknown }
  | { const: number }
  | { var: 'entry_price' };

type Kind = 'field' | 'indicator' | 'const' | 'var';

function kindOf(expr: Expression): Kind {
  if ('field' in expr) return 'field';
  if ('indicator' in expr) return 'indicator';
  if ('const' in expr) return 'const';
  return 'var';
}

interface Props {
  value: Expression;
  onChange: (v: Expression) => void;
  schema: DslSchema;
  allowEntryPrice: boolean;
}

const KIND_LABELS: Record<Kind, string> = {
  field:     '欄位',
  indicator: '指標',
  const:     '常數',
  var:       '進場價',
};

export function ExpressionPicker({ value, onChange, schema, allowEntryPrice }: Props) {
  const currentKind = kindOf(value);

  const kinds = useMemo<Kind[]>(() => {
    const out: Kind[] = ['field', 'indicator', 'const'];
    if (allowEntryPrice) out.push('var');
    return out;
  }, [allowEntryPrice]);

  function changeKind(k: Kind) {
    if (k === 'field')     onChange({ field: schema.fields[0] ?? 'close' });
    else if (k === 'indicator') {
      const ind = schema.indicators[0];
      const params: Record<string, unknown> = { indicator: ind.name };
      ind.params.forEach((p) => {
        params[p.name] =
          p.default !== undefined ? p.default :
          p.type === 'enum' ? p.choices?.[0] ?? '' :
          p.type === 'int' ? (p.min ?? 1) :
          (p.min ?? 1);
      });
      onChange(params as Expression);
    }
    else if (k === 'const') onChange({ const: 0 });
    else                    onChange({ var: 'entry_price' });
  }

  return (
    <div className="flex items-center gap-2">
      <Select value={currentKind} onValueChange={(v) => changeKind(v as Kind)}>
        <SelectTrigger className="w-24" aria-label="表達式種類">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {kinds.map((k) => (
            <SelectItem
              key={k}
              value={k}
              role="option"
              aria-label={KIND_LABELS[k]}
            >
              {KIND_LABELS[k]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {currentKind === 'field' && (
        <Select
          value={(value as { field: string }).field}
          onValueChange={(f) => onChange({ field: f })}
        >
          <SelectTrigger className="w-24" aria-label="欄位">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {schema.fields.map((f) => (
              <SelectItem key={f} value={f}>{f}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {currentKind === 'indicator' && (
        <IndicatorParamsRow
          value={value as { indicator: string; [k: string]: unknown }}
          onChange={onChange}
          schema={schema}
        />
      )}

      {currentKind === 'const' && (
        <Input
          type="number"
          step="any"
          className="w-32"
          aria-label="常數"
          value={(value as { const: number }).const}
          onChange={(e) => onChange({ const: Number(e.target.value) })}
        />
      )}

      {currentKind === 'var' && (
        <span className="text-sm text-muted-foreground">entry_price</span>
      )}
    </div>
  );
}

function IndicatorParamsRow({
  value, onChange, schema,
}: {
  value: { indicator: string; [k: string]: unknown };
  onChange: (v: Expression) => void;
  schema: DslSchema;
}) {
  const ind = schema.indicators.find((i) => i.name === value.indicator);
  if (!ind) return null;

  return (
    <div className="flex items-center gap-1">
      <Select
        value={value.indicator}
        onValueChange={(name) => {
          const next = schema.indicators.find((i) => i.name === name);
          if (!next) return;
          const out: Record<string, unknown> = { indicator: name };
          next.params.forEach((p) => {
            out[p.name] =
              p.default !== undefined ? p.default :
              p.type === 'enum' ? p.choices?.[0] ?? '' :
              p.type === 'int' ? (p.min ?? 1) :
              (p.min ?? 1);
          });
          onChange(out as Expression);
        }}
      >
        <SelectTrigger className="w-32" aria-label="指標">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {schema.indicators.map((i) => (
            <SelectItem key={i.name} value={i.name}>{i.name}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {ind.params.map((p) =>
        p.type === 'enum' ? (
          <Select
            key={p.name}
            value={String(value[p.name])}
            onValueChange={(v) => onChange({ ...value, [p.name]: v } as Expression)}
          >
            <SelectTrigger className="w-24" aria-label={p.name}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(p.choices ?? []).map((c) => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Input
            key={p.name}
            type="number"
            className="w-20"
            aria-label={p.name}
            value={Number(value[p.name] ?? 0)}
            onChange={(e) =>
              onChange({ ...value, [p.name]: Number(e.target.value) } as Expression)
            }
          />
        ),
      )}
    </div>
  );
}
```

Create `frontend/src/components/strategy/ConditionRow.tsx`:

```tsx
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Trash2 } from 'lucide-react';
import { ExpressionPicker, type Expression } from './ExpressionPicker';
import { OperatorSelect } from './OperatorSelect';
import type { DslSchema } from '@/hooks/useStrategy';

export interface DslCondition {
  left:  Expression;
  op:    string;
  right: Expression;
  n?:    number;
}

interface Props {
  value: DslCondition;
  onChange: (v: DslCondition) => void;
  onDelete: () => void;
  schema: DslSchema;
  allowEntryPrice: boolean;
}

export function ConditionRow({
  value, onChange, onDelete, schema, allowEntryPrice,
}: Props) {
  const isStreak =
    value.op === 'streak_above' || value.op === 'streak_below';

  return (
    <div className="flex flex-wrap items-center gap-2 py-1">
      <ExpressionPicker
        value={value.left}
        onChange={(left) => onChange({ ...value, left })}
        schema={schema}
        allowEntryPrice={allowEntryPrice}
      />
      <OperatorSelect
        value={value.op}
        onChange={(op) => {
          const next: DslCondition = { ...value, op };
          if (op === 'streak_above' || op === 'streak_below') {
            next.n = next.n ?? 3;
          } else {
            delete next.n;
          }
          onChange(next);
        }}
        operators={schema.operators}
      />
      {isStreak && (
        <Input
          type="number"
          min={1}
          className="w-16"
          aria-label="n"
          value={value.n ?? 3}
          onChange={(e) =>
            onChange({ ...value, n: Math.max(1, Number(e.target.value)) })
          }
        />
      )}
      <ExpressionPicker
        value={value.right}
        onChange={(right) => onChange({ ...value, right })}
        schema={schema}
        allowEntryPrice={allowEntryPrice}
      />
      <Button
        type="button"
        size="icon"
        variant="ghost"
        aria-label="刪除條件"
        onClick={onDelete}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}
```

Create `frontend/src/components/strategy/ConditionBuilder.tsx`:

```tsx
import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';
import { ConditionRow, type DslCondition } from './ConditionRow';
import type { DslSchema } from '@/hooks/useStrategy';

interface Props {
  value: DslCondition[];
  onChange: (v: DslCondition[]) => void;
  schema: DslSchema;
  /** True only inside the take_profit / stop_loss "advanced" editor;
   *  entry conditions cannot reference {var: entry_price}. */
  allowEntryPrice?: boolean;
  maxConditions?: number;
}

export function ConditionBuilder({
  value, onChange, schema,
  allowEntryPrice = false, maxConditions = 5,
}: Props) {
  const addCondition = () => {
    const initial: DslCondition = {
      left:  { field: schema.fields[0] ?? 'close' },
      op:    schema.operators[0] ?? 'gt',
      right: { const: 0 },
    };
    onChange([...value, initial]);
  };

  return (
    <div className="space-y-1">
      {value.map((c, i) => (
        <ConditionRow
          key={i}
          value={c}
          onChange={(updated) => {
            const copy = [...value];
            copy[i] = updated;
            onChange(copy);
          }}
          onDelete={() => onChange(value.filter((_, idx) => idx !== i))}
          schema={schema}
          allowEntryPrice={allowEntryPrice}
        />
      ))}
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={addCondition}
        disabled={value.length >= maxConditions}
      >
        <Plus className="h-4 w-4 mr-1" />
        新增條件
      </Button>
      {value.length >= maxConditions && (
        <p className="text-xs text-muted-foreground">
          已達 {maxConditions} 條上限。再多通常代表過度擬合。
        </p>
      )}
    </div>
  );
}
```

Create `frontend/src/components/strategy/ExitConditionEditor.tsx`:

```tsx
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ConditionBuilder } from './ConditionBuilder';
import type { DslCondition } from './ConditionRow';
import type { DslSchema } from '@/hooks/useStrategy';

export type ExitDsl =
  | { version: 1; type: 'pct';    value: number }
  | { version: 1; type: 'points'; value: number }
  | { version: 1; type: 'dsl';    all:   DslCondition[] };

interface Props {
  value: ExitDsl;
  onChange: (v: ExitDsl) => void;
  schema: DslSchema;
}

export function ExitConditionEditor({ value, onChange, schema }: Props) {
  function setMode(mode: ExitDsl['type']) {
    if (mode === 'pct')    onChange({ version: 1, type: 'pct',    value: 2.0 });
    else if (mode === 'points') onChange({ version: 1, type: 'points', value: 50 });
    else                  onChange({ version: 1, type: 'dsl',    all:   [] });
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-1" role="tablist" aria-label="出場模式">
        <Button
          type="button" size="sm"
          variant={value.type === 'pct'    ? 'default' : 'outline'}
          role="tab" aria-selected={value.type === 'pct'}
          onClick={() => setMode('pct')}
        >百分比</Button>
        <Button
          type="button" size="sm"
          variant={value.type === 'points' ? 'default' : 'outline'}
          role="tab" aria-selected={value.type === 'points'}
          onClick={() => setMode('points')}
        >點數</Button>
        <Button
          type="button" size="sm"
          variant={value.type === 'dsl'    ? 'default' : 'outline'}
          role="tab" aria-selected={value.type === 'dsl'}
          onClick={() => setMode('dsl')}
        >進階</Button>
      </div>

      {value.type === 'pct' && (
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground" htmlFor="exit-pct">
            百分比 (%)
          </label>
          <Input
            id="exit-pct"
            type="number"
            step="0.1"
            min={0}
            className="w-24"
            value={value.value}
            onChange={(e) =>
              onChange({ version: 1, type: 'pct', value: Number(e.target.value) })
            }
          />
        </div>
      )}

      {value.type === 'points' && (
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground" htmlFor="exit-points">
            點數
          </label>
          <Input
            id="exit-points"
            type="number"
            step="1"
            min={0}
            className="w-24"
            value={value.value}
            onChange={(e) =>
              onChange({ version: 1, type: 'points', value: Number(e.target.value) })
            }
          />
        </div>
      )}

      {value.type === 'dsl' && (
        <ConditionBuilder
          value={value.all}
          onChange={(all) => onChange({ version: 1, type: 'dsl', all })}
          schema={schema}
          allowEntryPrice={true}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2.4: Run tests — should pass**

```bash
cd /Users/paulwu/Documents/Github/publixia/frontend
npm test -- strategy 2>&1 | tail -10
```

Expected: 7 tests PASS (4 ConditionBuilder + 3 ExitConditionEditor).

- [ ] **Step 2.5: Run full frontend suite**

```bash
npm test 2>&1 | tail -10
```

Expected: full suite green.

- [ ] **Step 2.6: Build still compiles**

```bash
npm run build 2>&1 | tail -3
```

Expected: success.

- [ ] **Step 2.7: Commit**

```bash
cd /Users/paulwu/Documents/Github/publixia
git add frontend/src/components/strategy/ExpressionPicker.tsx \
        frontend/src/components/strategy/OperatorSelect.tsx \
        frontend/src/components/strategy/ConditionRow.tsx \
        frontend/src/components/strategy/ConditionBuilder.tsx \
        frontend/src/components/strategy/ExitConditionEditor.tsx \
        frontend/tests/strategy/ConditionBuilder.test.tsx \
        frontend/tests/strategy/ExitConditionEditor.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): DSL builder components

ConditionBuilder + ConditionRow + ExpressionPicker + OperatorSelect +
ExitConditionEditor cover the full DSL grammar from the P2 schema.
ExpressionPicker handles all four expr kinds (field/indicator/const/var)
with entry_price hidden when allowEntryPrice is false (entry conditions
forbidden by spec §4.4 / §5 validator).

ExitConditionEditor toggles pct / points / advanced modes; advanced
delegates back to ConditionBuilder with allowEntryPrice=true so users
can write "close < entry_price"-style stop rules.
EOF
)"
```

---

## Task 3 — List page + delete + nav wiring

**Files:**
- Modify: `frontend/src/pages/StrategiesListPage.tsx` (replace placeholder)
- Modify: `frontend/src/pages/DashboardPage.tsx` (insert nav link)
- Create: `frontend/tests/strategy/StrategiesListPage.test.tsx`

The list page reads `useStrategies()`, renders each as a card with state badge + actions, and links to the edit page. A "建立策略" button at the top routes to `/strategies/new`.

- [ ] **Step 3.1: Write the failing test**

Create `frontend/tests/strategy/StrategiesListPage.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../setup';
import StrategiesListPage from '../../src/pages/StrategiesListPage';

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/strategies']}>
        <Routes>
          <Route path="/strategies" element={<StrategiesListPage />} />
          <Route path="/strategies/new" element={<div>NEW PAGE</div>} />
          <Route path="/strategies/:id" element={<div>EDIT PAGE</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('StrategiesListPage', () => {
  it('renders the empty state when there are no strategies', async () => {
    server.use(
      http.get('*/api/strategies', () => HttpResponse.json([])),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/還沒有策略/)).toBeInTheDocument(),
    );
  });

  it('renders one card per strategy with state badge + name', async () => {
    server.use(
      http.get('*/api/strategies', () =>
        HttpResponse.json([
          {
            id: 1, user_id: 1,
            name: 'rsi_long', direction: 'long', contract: 'TX',
            contract_size: 1, max_hold_days: null,
            entry_dsl: {}, take_profit_dsl: {}, stop_loss_dsl: {},
            notify_enabled: true,
            state: 'open',
            entry_signal_date: '2026-05-01', entry_fill_date: '2026-05-02',
            entry_fill_price: 17000, pending_exit_kind: null,
            pending_exit_signal_date: null,
            last_error: null, last_error_at: null,
            created_at: '2026-04-01', updated_at: '2026-05-02',
          },
        ]),
      ),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByText('rsi_long')).toBeInTheDocument(),
    );
    expect(screen.getByText(/在場內/)).toBeInTheDocument();
  });

  it('the "建立策略" button links to /strategies/new', async () => {
    server.use(
      http.get('*/api/strategies', () => HttpResponse.json([])),
    );
    renderPage();
    const link = await screen.findByRole('link', { name: /建立策略/ });
    expect(link).toHaveAttribute('href', '/strategies/new');
  });
});
```

- [ ] **Step 3.2: Run — should fail**

```bash
cd /Users/paulwu/Documents/Github/publixia/frontend
npm test -- strategy/StrategiesListPage 2>&1 | tail -15
```

Expected: failures because the placeholder page doesn't render the test fixture.

- [ ] **Step 3.3: Replace `StrategiesListPage.tsx`**

```tsx
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
```

- [ ] **Step 3.4: Add the nav link to `DashboardPage`**

Open `frontend/src/pages/DashboardPage.tsx`. At the top of the file with other imports add:

```tsx
import { StrategiesNavLink } from '@/components/strategy/NavLink';
```

Find the existing header `<div className="flex items-center justify-between">` block (around the `<DashboardSettingsDialog />`):

```tsx
<div className="flex items-center justify-between">
  <h1 className="text-2xl font-bold">Dashboard</h1>
  <DashboardSettingsDialog />
</div>
```

Replace with:

```tsx
<div className="flex items-center justify-between">
  <div className="flex items-center gap-4">
    <h1 className="text-2xl font-bold">Dashboard</h1>
    <StrategiesNavLink />
  </div>
  <DashboardSettingsDialog />
</div>
```

- [ ] **Step 3.5: Run tests**

```bash
npm test -- strategy/StrategiesListPage 2>&1 | tail -10
npm test 2>&1 | tail -10
```

Expected: 3 new tests PASS, full frontend suite green.

- [ ] **Step 3.6: Build**

```bash
npm run build 2>&1 | tail -3
```

Expected: success.

- [ ] **Step 3.7: Commit**

```bash
cd /Users/paulwu/Documents/Github/publixia
git add frontend/src/pages/StrategiesListPage.tsx \
        frontend/src/pages/DashboardPage.tsx \
        frontend/tests/strategy/StrategiesListPage.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): strategies list page + dashboard nav link

List renders one card per strategy with the state badge (idle / 待進場
/ 在場內 / 待出場), direction · contract · lots, notify_enabled flag,
and a truncated last_error if any. Card title links to the edit page.
"建立策略" button routes to /strategies/new. Empty state guides the
user to the create button. Delete button confirms before mutating.

Dashboard header gains the StrategiesNavLink (rendered only when
useMe.can_use_strategy is true).
EOF
)"
```

---

## Task 4 — Edit page (form + state + signal history + force_close + reset + enable/disable)

**Files:**
- Modify: `frontend/src/pages/StrategyEditPage.tsx`
- Create: `frontend/src/components/strategy/StrategyForm.tsx`
- Create: `frontend/src/components/strategy/PositionStatusCard.tsx`
- Create: `frontend/src/components/strategy/SignalHistoryTable.tsx`
- Create: `frontend/tests/strategy/StrategyForm.test.tsx`

The edit page handles both create (`/strategies/new`) and edit (`/strategies/:id`) modes. Backtest panel lives in Task 5.

- [ ] **Step 4.1: Write the failing form test**

Create `frontend/tests/strategy/StrategyForm.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StrategyForm } from '../../src/components/strategy/StrategyForm';
import type { DslSchema } from '../../src/hooks/useStrategy';

const SCHEMA: DslSchema = {
  version: 1,
  fields: ['close', 'high', 'low'],
  operators: ['gt', 'lt'],
  indicators: [
    { name: 'sma', params: [{ name: 'n', type: 'int', min: 1, default: 20 }] },
  ],
  exit_modes: ['pct', 'points', 'dsl'],
  vars: ['entry_price'],
};

describe('StrategyForm', () => {
  it('renders all required metadata inputs in create mode', () => {
    render(
      <StrategyForm
        schema={SCHEMA}
        mode="create"
        onSubmit={() => {}}
      />,
    );
    expect(screen.getByLabelText(/名稱/)).toBeInTheDocument();
    expect(screen.getByLabelText(/方向/)).toBeInTheDocument();
    expect(screen.getByLabelText(/商品/)).toBeInTheDocument();
    expect(screen.getByLabelText(/口數/)).toBeInTheDocument();
  });

  it('blocks submit with empty name in create mode', () => {
    const calls: unknown[] = [];
    render(
      <StrategyForm
        schema={SCHEMA}
        mode="create"
        onSubmit={(v) => calls.push(v)}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /儲存/ }));
    expect(calls.length).toBe(0);
    expect(screen.getByText(/請輸入名稱/)).toBeInTheDocument();
  });

  it('emits a payload with sensible defaults on first submit', () => {
    const calls: unknown[] = [];
    render(
      <StrategyForm
        schema={SCHEMA}
        mode="create"
        onSubmit={(v) => calls.push(v)}
      />,
    );
    fireEvent.change(screen.getByLabelText(/名稱/), { target: { value: 's1' } });
    // Add an entry condition so submit isn't blocked by empty list.
    fireEvent.click(screen.getByRole('button', { name: /新增條件/ }));
    fireEvent.click(screen.getByRole('button', { name: /儲存/ }));
    expect(calls).toHaveLength(1);
    const payload = calls[0] as Record<string, unknown>;
    expect(payload.name).toBe('s1');
    expect(payload.contract).toBe('TX');
    expect(payload.contract_size).toBe(1);
  });

  it('freezes DSL fields when initial.state != idle (edit mode)', () => {
    render(
      <StrategyForm
        schema={SCHEMA}
        mode="edit"
        initial={{
          name: 'in_pos', direction: 'long', contract: 'TX',
          contract_size: 1, max_hold_days: null,
          entry_dsl: { version: 1, all: [
            { left: { field: 'close' }, op: 'gt', right: { const: 100 } },
          ]},
          take_profit_dsl: { version: 1, type: 'pct', value: 2.0 },
          stop_loss_dsl:   { version: 1, type: 'pct', value: 1.0 },
          state: 'open',
        }}
        onSubmit={() => {}}
      />,
    );
    expect(screen.getByText(/在場內,條件已凍結/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 4.2: Run — should fail**

```bash
npm test -- strategy/StrategyForm 2>&1 | tail -10
```

Expected: import error.

- [ ] **Step 4.3: Implement `PositionStatusCard`**

Create `frontend/src/components/strategy/PositionStatusCard.tsx`:

```tsx
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
```

- [ ] **Step 4.4: Implement `SignalHistoryTable`**

Create `frontend/src/components/strategy/SignalHistoryTable.tsx`:

```tsx
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import type { SignalRecord } from '@/hooks/useStrategy';

const KIND_LABELS: Record<SignalRecord['kind'], string> = {
  ENTRY_SIGNAL:  '📈 進場訊號',
  ENTRY_FILLED:  '✅ 進場結算',
  EXIT_SIGNAL:   '⚠️ 出場訊號',
  EXIT_FILLED:   '🏁 出場結算',
  MANUAL_RESET:  '🔧 手動重置',
  RUNTIME_ERROR: '❌ 執行錯誤',
};

export function SignalHistoryTable({ signals }: { signals: SignalRecord[] }) {
  if (!signals.length) {
    return (
      <p className="text-sm text-muted-foreground">
        尚無訊號歷史。
      </p>
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>類型</TableHead>
          <TableHead>日期</TableHead>
          <TableHead className="text-right">close</TableHead>
          <TableHead className="text-right">成交價</TableHead>
          <TableHead>原因</TableHead>
          <TableHead className="text-right">PnL (點)</TableHead>
          <TableHead className="text-right">PnL (NTD)</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {signals.map((s) => (
          <TableRow key={s.id}>
            <TableCell>{KIND_LABELS[s.kind] ?? s.kind}</TableCell>
            <TableCell>{s.signal_date}</TableCell>
            <TableCell className="text-right">
              {s.close_at_signal !== null ? s.close_at_signal.toLocaleString() : '—'}
            </TableCell>
            <TableCell className="text-right">
              {s.fill_price !== null ? s.fill_price.toLocaleString() : '—'}
            </TableCell>
            <TableCell>{s.exit_reason ?? '—'}</TableCell>
            <TableCell className="text-right">
              {s.pnl_points !== null ? s.pnl_points.toFixed(2) : '—'}
            </TableCell>
            <TableCell className="text-right">
              {s.pnl_amount !== null ? s.pnl_amount.toLocaleString() : '—'}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 4.5: Implement `StrategyForm`**

Create `frontend/src/components/strategy/StrategyForm.tsx`:

```tsx
import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { ConditionBuilder } from './ConditionBuilder';
import { ExitConditionEditor, type ExitDsl } from './ExitConditionEditor';
import type { DslCondition } from './ConditionRow';
import type {
  DslSchema, StrategyCreatePayload, StrategyUpdatePayload, Strategy,
} from '@/hooks/useStrategy';

interface Initial {
  name: string;
  direction: 'long' | 'short';
  contract: 'TX' | 'MTX' | 'TMF';
  contract_size: number;
  max_hold_days: number | null;
  entry_dsl: { version: 1; all: DslCondition[] };
  take_profit_dsl: ExitDsl;
  stop_loss_dsl: ExitDsl;
  state?: Strategy['state'];
}

interface Props {
  schema: DslSchema;
  mode: 'create' | 'edit';
  initial?: Initial;
  onSubmit: (payload: StrategyCreatePayload | StrategyUpdatePayload) => void;
  saving?: boolean;
  serverError?: string | null;
}

const DEFAULT: Initial = {
  name: '',
  direction: 'long',
  contract: 'TX',
  contract_size: 1,
  max_hold_days: null,
  entry_dsl:       { version: 1, all: [] },
  take_profit_dsl: { version: 1, type: 'pct', value: 2.0 },
  stop_loss_dsl:   { version: 1, type: 'pct', value: 1.0 },
};

export function StrategyForm({
  schema, mode, initial, onSubmit, saving, serverError,
}: Props) {
  const [state, setState] = useState<Initial>(initial ?? DEFAULT);
  const [validationError, setValidationError] = useState<string | null>(null);
  const inPosition = mode === 'edit' && state.state !== undefined && state.state !== 'idle';

  const handleSubmit = () => {
    if (!state.name.trim()) {
      setValidationError('請輸入名稱');
      return;
    }
    if (state.entry_dsl.all.length === 0) {
      setValidationError('進場條件至少需要一條規則');
      return;
    }
    setValidationError(null);
    onSubmit({
      name: state.name.trim(),
      direction: state.direction,
      contract: state.contract,
      contract_size: state.contract_size,
      max_hold_days: state.max_hold_days,
      entry_dsl: state.entry_dsl,
      take_profit_dsl: state.take_profit_dsl,
      stop_loss_dsl: state.stop_loss_dsl,
    });
  };

  return (
    <div className="space-y-4">
      {inPosition && (
        <div className="text-sm text-amber-700 bg-amber-500/10 p-2 rounded">
          策略目前在場內,條件已凍結。如需調整條件請先「重置」或「強制平倉」。
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <label htmlFor="strat-name" className="text-sm">名稱</label>
          <Input
            id="strat-name"
            aria-label="名稱"
            value={state.name}
            onChange={(e) => setState({ ...state, name: e.target.value })}
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="strat-direction" className="text-sm">方向</label>
          <Select
            value={state.direction}
            onValueChange={(v) =>
              setState({ ...state, direction: v as 'long' | 'short' })
            }
            disabled={inPosition}
          >
            <SelectTrigger id="strat-direction" aria-label="方向">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="long">多 (long)</SelectItem>
              <SelectItem value="short">空 (short)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <label htmlFor="strat-contract" className="text-sm">商品</label>
          <Select
            value={state.contract}
            onValueChange={(v) =>
              setState({ ...state, contract: v as 'TX' | 'MTX' | 'TMF' })
            }
            disabled={inPosition}
          >
            <SelectTrigger id="strat-contract" aria-label="商品">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="TX">大台 (TX)</SelectItem>
              <SelectItem value="MTX">小台 (MTX)</SelectItem>
              <SelectItem value="TMF">微台 (TMF)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <label htmlFor="strat-size" className="text-sm">口數</label>
          <Input
            id="strat-size"
            aria-label="口數"
            type="number"
            min={1}
            value={state.contract_size}
            onChange={(e) =>
              setState({ ...state, contract_size: Math.max(1, Number(e.target.value)) })
            }
          />
        </div>

        <div className="space-y-1 sm:col-span-2">
          <label htmlFor="strat-max-hold" className="text-sm">
            最大持倉天數 (留空 = 不限)
          </label>
          <Input
            id="strat-max-hold"
            type="number"
            min={1}
            value={state.max_hold_days ?? ''}
            disabled={inPosition}
            onChange={(e) =>
              setState({
                ...state,
                max_hold_days: e.target.value ? Number(e.target.value) : null,
              })
            }
          />
        </div>
      </div>

      <fieldset disabled={inPosition} className="space-y-2">
        <legend className="text-sm font-medium">進場條件 (AND)</legend>
        <ConditionBuilder
          schema={schema}
          value={state.entry_dsl.all}
          onChange={(all) => setState({ ...state, entry_dsl: { version: 1, all } })}
          allowEntryPrice={false}
        />
      </fieldset>

      <fieldset disabled={inPosition} className="space-y-2">
        <legend className="text-sm font-medium">停利</legend>
        <ExitConditionEditor
          schema={schema}
          value={state.take_profit_dsl}
          onChange={(take_profit_dsl) => setState({ ...state, take_profit_dsl })}
        />
      </fieldset>

      <fieldset disabled={inPosition} className="space-y-2">
        <legend className="text-sm font-medium">停損</legend>
        <ExitConditionEditor
          schema={schema}
          value={state.stop_loss_dsl}
          onChange={(stop_loss_dsl) => setState({ ...state, stop_loss_dsl })}
        />
      </fieldset>

      {(validationError || serverError) && (
        <div className="text-destructive text-sm">
          {validationError ?? serverError}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button
          type="button"
          onClick={handleSubmit}
          disabled={saving || (inPosition && mode === 'edit' &&
            // metadata-only edits are allowed in-position; checked server-side
            false)}
        >
          {saving ? '儲存中…' : '儲存'}
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4.6: Implement the page**

Replace `frontend/src/pages/StrategyEditPage.tsx`:

```tsx
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  useStrategy, useStrategySignals, useDslSchema,
  useCreateStrategy, useUpdateStrategy,
  useEnableStrategy, useDisableStrategy,
  useForceCloseStrategy, useResetStrategy, useMe,
} from '@/hooks/useStrategy';
import { ApiError } from '@/lib/api-client';
import { StrategyForm } from '@/components/strategy/StrategyForm';
import { PositionStatusCard } from '@/components/strategy/PositionStatusCard';
import { SignalHistoryTable } from '@/components/strategy/SignalHistoryTable';
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

  const handleSubmit = (payload: Parameters<typeof create.mutate>[0]) => {
    setServerError(null);
    if (isEdit) {
      update.mutate(payload, {
        onError: (e: unknown) => setServerError(e instanceof ApiError ? e.message : '儲存失敗'),
      });
    } else {
      create.mutate(payload, {
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
    </div>
  );
}
```

- [ ] **Step 4.7: Run tests**

```bash
npm test -- strategy/StrategyForm 2>&1 | tail -10
npm test 2>&1 | tail -10
```

Expected: 4 new form tests PASS; full suite green.

- [ ] **Step 4.8: Build**

```bash
npm run build 2>&1 | tail -3
```

Expected: success.

- [ ] **Step 4.9: Commit**

```bash
cd /Users/paulwu/Documents/Github/publixia
git add frontend/src/pages/StrategyEditPage.tsx \
        frontend/src/components/strategy/StrategyForm.tsx \
        frontend/src/components/strategy/PositionStatusCard.tsx \
        frontend/src/components/strategy/SignalHistoryTable.tsx \
        frontend/tests/strategy/StrategyForm.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): strategy edit page with form + state + signals

StrategyEditPage handles both create and edit modes (route param id
absent vs present). PositionStatusCard renders the four state values
+ entry price/date/last_error and surfaces force_close (only when in
position) + reset (always). Notification toggle is disabled if the
user has no webhook (useMe.has_webhook=false). DSL fields are frozen
in <fieldset disabled> while strategy.state != idle (matches P4
backend's PATCH 422 rule). SignalHistoryTable renders the latest 50
rows with kind icons + PnL. Server-side errors from create/update
surface inline.
EOF
)"
```

---

## Task 5 — Backtest panel + equity curve chart

**Files:**
- Create: `frontend/src/components/strategy/BacktestPanel.tsx`
- Create: `frontend/src/components/strategy/EquityCurveChart.tsx`
- Modify: `frontend/src/pages/StrategyEditPage.tsx` (mount BacktestPanel)
- Create: `frontend/tests/strategy/BacktestPanel.test.tsx`

The panel POSTs `/api/strategies/{id}/backtest` with a date range, then renders the response: summary cards (total PnL, win rate, profit factor, max drawdown) + the trades table + the equity-curve chart (cumulative `pnl_amount` plotted against `exit_date`).

- [ ] **Step 5.1: Write the failing tests**

Create `frontend/tests/strategy/BacktestPanel.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '../setup';
import { BacktestPanel } from '../../src/components/strategy/BacktestPanel';

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>{node}</QueryClientProvider>
  );
}

describe('BacktestPanel', () => {
  it('renders the date range form + run button', () => {
    render(wrap(<BacktestPanel strategyId={1} />));
    expect(screen.getByLabelText(/開始日期/)).toBeInTheDocument();
    expect(screen.getByLabelText(/結束日期/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /執行回測/ })).toBeInTheDocument();
  });

  it('runs a backtest and renders summary + trades on success', async () => {
    server.use(
      http.post('*/api/strategies/1/backtest', () =>
        HttpResponse.json({
          trades: [{
            entry_date: '2026-02-01', entry_price: 17000,
            exit_date:  '2026-02-10', exit_price:  17200,
            exit_reason: 'TAKE_PROFIT', held_bars: 7,
            pnl_points: 200, pnl_amount: 40000, from_stop: false,
          }],
          summary: {
            total_pnl_amount: 40000, win_rate: 100,
            avg_win_points: 200, avg_loss_points: 0,
            profit_factor: 0, max_drawdown_amt: 0,
            max_drawdown_pct: 0, n_trades: 1, avg_held_bars: 7,
          },
          warnings: [],
        }),
      ),
    );
    render(wrap(<BacktestPanel strategyId={1} />));
    fireEvent.click(screen.getByRole('button', { name: /執行回測/ }));
    await waitFor(() =>
      expect(screen.getByText(/總損益/)).toBeInTheDocument(),
    );
    expect(screen.getByText('TAKE_PROFIT')).toBeInTheDocument();
  });

  it('renders warnings when the API returns them', async () => {
    server.use(
      http.post('*/api/strategies/1/backtest', () =>
        HttpResponse.json({
          trades: [],
          summary: {
            total_pnl_amount: 0, win_rate: 0,
            avg_win_points: 0, avg_loss_points: 0,
            profit_factor: 0, max_drawdown_amt: 0,
            max_drawdown_pct: 0, n_trades: 0, avg_held_bars: 0,
          },
          warnings: ['no bars in futures_daily for contract=TX between 2026-01-01 and 2026-02-01'],
        }),
      ),
    );
    render(wrap(<BacktestPanel strategyId={1} />));
    fireEvent.click(screen.getByRole('button', { name: /執行回測/ }));
    await waitFor(() =>
      expect(screen.getByText(/no bars in futures_daily/)).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 5.2: Run — should fail**

```bash
npm test -- strategy/BacktestPanel 2>&1 | tail -10
```

Expected: import error.

- [ ] **Step 5.3: Implement `EquityCurveChart`**

Create `frontend/src/components/strategy/EquityCurveChart.tsx`:

```tsx
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import type { BacktestTrade } from '@/hooks/useStrategy';

export function EquityCurveChart({ trades }: { trades: BacktestTrade[] }) {
  if (!trades.length) return null;

  const points: { date: string; cumulative: number }[] = [];
  let cumulative = 0;
  for (const t of trades) {
    cumulative += t.pnl_amount;
    points.push({ date: t.exit_date, cumulative });
  }

  return (
    <div style={{ width: '100%', height: 240 }}>
      <ResponsiveContainer>
        <LineChart data={points} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis
            tick={{ fontSize: 11 }}
            tickFormatter={(v) => v.toLocaleString()}
          />
          <Tooltip
            formatter={(v: number) => v.toLocaleString()}
            labelFormatter={(d) => `出場日:${d}`}
          />
          <Line
            type="monotone"
            dataKey="cumulative"
            name="累計 PnL"
            stroke="#10b981"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 5.4: Implement `BacktestPanel`**

Create `frontend/src/components/strategy/BacktestPanel.tsx`:

```tsx
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { useBacktest, type BacktestResponse } from '@/hooks/useStrategy';
import { ApiError } from '@/lib/api-client';
import { EquityCurveChart } from './EquityCurveChart';

interface Props {
  strategyId: number;
}

function defaultRange(): { start: string; end: string } {
  const today = new Date();
  const start = new Date(today.getFullYear() - 5, today.getMonth(), today.getDate());
  return {
    start: start.toISOString().slice(0, 10),
    end:   today.toISOString().slice(0, 10),
  };
}

export function BacktestPanel({ strategyId }: Props) {
  const range = defaultRange();
  const [startDate, setStartDate] = useState(range.start);
  const [endDate,   setEndDate]   = useState(range.end);
  const [result,    setResult]    = useState<BacktestResponse | null>(null);
  const [error,     setError]     = useState<string | null>(null);

  const backtest = useBacktest(strategyId);

  const run = () => {
    setError(null);
    backtest.mutate(
      { start_date: startDate, end_date: endDate },
      {
        onSuccess: (r) => setResult(r),
        onError: (e: unknown) =>
          setError(e instanceof ApiError ? e.message : '回測失敗'),
      },
    );
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label htmlFor="bt-start" className="text-sm">開始日期</label>
          <Input
            id="bt-start"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="bt-end" className="text-sm">結束日期</label>
          <Input
            id="bt-end"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>
        <Button onClick={run} disabled={backtest.isPending}>
          {backtest.isPending ? '計算中…' : '執行回測'}
        </Button>
      </div>

      {error && <p className="text-destructive text-sm">{error}</p>}
      {result?.warnings.length ? (
        <ul className="text-amber-700 text-sm list-disc pl-5">
          {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      ) : null}

      {result && <BacktestSummaryCards summary={result.summary} />}
      {result && result.trades.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">累計權益曲線</CardTitle>
          </CardHeader>
          <CardContent>
            <EquityCurveChart trades={result.trades} />
          </CardContent>
        </Card>
      )}
      {result && result.trades.length > 0 && <BacktestTradesTable result={result} />}
    </div>
  );
}

function BacktestSummaryCards({ summary }: { summary: BacktestResponse['summary'] }) {
  const cards = [
    { label: '總損益 (NTD)',    value: summary.total_pnl_amount.toLocaleString() },
    { label: '勝率',           value: `${summary.win_rate.toFixed(1)}%` },
    { label: '交易次數',       value: summary.n_trades },
    { label: '平均持倉 (bars)', value: summary.avg_held_bars.toFixed(1) },
    { label: '盈虧比',         value: summary.profit_factor === 0 ? '—' : summary.profit_factor.toFixed(2) },
    { label: '最大回撤',       value: summary.max_drawdown_amt.toLocaleString() },
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
      {cards.map((c) => (
        <Card key={c.label}>
          <CardContent className="p-3">
            <p className="text-xs text-muted-foreground">{c.label}</p>
            <p className="text-lg font-semibold">{c.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function BacktestTradesTable({ result }: { result: BacktestResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">交易明細</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>進場日</TableHead>
              <TableHead className="text-right">進場價</TableHead>
              <TableHead>出場日</TableHead>
              <TableHead className="text-right">出場價</TableHead>
              <TableHead>原因</TableHead>
              <TableHead className="text-right">PnL (點)</TableHead>
              <TableHead className="text-right">PnL (NTD)</TableHead>
              <TableHead className="text-right">持倉 (bars)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {result.trades.map((t, i) => (
              <TableRow key={i}>
                <TableCell>{t.entry_date}</TableCell>
                <TableCell className="text-right">{t.entry_price.toLocaleString()}</TableCell>
                <TableCell>{t.exit_date}</TableCell>
                <TableCell className="text-right">{t.exit_price.toLocaleString()}</TableCell>
                <TableCell>{t.exit_reason}</TableCell>
                <TableCell className="text-right">{t.pnl_points.toFixed(2)}</TableCell>
                <TableCell className="text-right">{t.pnl_amount.toLocaleString()}</TableCell>
                <TableCell className="text-right">{t.held_bars}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 5.5: Mount the panel in the edit page**

Open `frontend/src/pages/StrategyEditPage.tsx` and add to the imports:

```tsx
import { BacktestPanel } from '@/components/strategy/BacktestPanel';
```

Find the `{isEdit && signals && ...}` signal-history block (the bottom of the page). Insert AFTER it:

```tsx
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
```

- [ ] **Step 5.6: Run tests**

```bash
npm test -- strategy/BacktestPanel 2>&1 | tail -10
npm test 2>&1 | tail -10
```

Expected: 3 new tests PASS; full frontend suite green.

- [ ] **Step 5.7: Build**

```bash
npm run build 2>&1 | tail -3
```

Expected: success.

- [ ] **Step 5.8: Commit**

```bash
cd /Users/paulwu/Documents/Github/publixia
git add frontend/src/components/strategy/BacktestPanel.tsx \
        frontend/src/components/strategy/EquityCurveChart.tsx \
        frontend/src/pages/StrategyEditPage.tsx \
        frontend/tests/strategy/BacktestPanel.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): backtest panel + equity curve chart

Date-range form posts to /api/strategies/{id}/backtest, then renders
6 summary cards (total PnL, win rate, n_trades, avg hold, profit
factor, max drawdown) + Recharts cumulative-PnL line + trades table.
Backend warnings (e.g. "no bars in range") surface as amber bullets.
Default range is the last 5 years to match the engine's lookback.
EOF
)"
```

---

## Phase exit criteria

After all five tasks are committed:

1. `cd frontend && npm test` passes (≈ 17 new strategy tests + existing).
2. `cd frontend && npm run build` succeeds.
3. `cd frontend && npm run dev` — manually verify against the deployed backend:
   - Header shows "策略" link only when `paul` has `can_use_strategy=1` (already true on VPS).
   - `/strategies` lists the empty state initially.
   - `/strategies/new` lets you build a SMA-cross strategy and save.
   - Detail page shows position status (idle), notification toggle (disabled because no webhook on VPS yet), signal history (empty), and backtest panel.
   - Backtest run on a real range produces a populated chart + summary.
4. `git log --oneline master..HEAD` shows the five phase commits.

Frontend is then ready to merge. Backend is unchanged — the deploy at master only swaps frontend assets via `deploy-frontend.yml`.

The next phase is **P6: integration + production rollout** — E2E test fixture using a fully-strategised paul row, ADMIN.md additions documenting the operator workflow, and any remaining P2.5/P3.5 cleanup.
