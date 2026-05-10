import { createBrowserRouter, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import DashboardPage from './pages/DashboardPage';
import StockDetailPage from './pages/StockDetailPage';
import FuturesDetailPage from './pages/FuturesDetailPage';
import Top100Page from './pages/Top100Page';
import { PermissionGate } from './components/strategy/PermissionGate';
import { Top100PermissionGate } from './components/top100/PermissionGate';
import { ForeignFuturesPermissionGate } from './components/foreign-futures/PermissionGate';

const StrategiesListPage = lazy(() => import('./pages/StrategiesListPage'));
const StrategyEditPage   = lazy(() => import('./pages/StrategyEditPage'));
const ForeignFuturesPage = lazy(() => import('./pages/ForeignFuturesPage'));

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
    {
      path: '/futures/tw/foreign-flow',
      element: (
        <ForeignFuturesPermissionGate>
          <Suspense fallback={<div className="p-8 text-muted-foreground">載入中…</div>}>
            <ForeignFuturesPage />
          </Suspense>
        </ForeignFuturesPermissionGate>
      ),
    },
    { path: '/tw-top100', element: <Top100PermissionGate><Top100Page /></Top100PermissionGate> },
    { path: '/strategies',         element: gated(<StrategiesListPage />) },
    { path: '/strategies/new',     element: gated(<StrategyEditPage />) },
    { path: '/strategies/:id',     element: gated(<StrategyEditPage />) },
    { path: '*', element: <Navigate to="/" replace /> },
  ]);
}
