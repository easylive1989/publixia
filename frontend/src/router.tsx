import { createBrowserRouter, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import DashboardPage from './pages/DashboardPage';
import StockDetailPage from './pages/StockDetailPage';
import FuturesDetailPage from './pages/FuturesDetailPage';
import Top100Page from './pages/Top100Page';
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
    { path: '/tw-top100', element: <Top100Page /> },
    { path: '/strategies',         element: gated(<StrategiesListPage />) },
    { path: '/strategies/new',     element: gated(<StrategyEditPage />) },
    { path: '/strategies/:id',     element: gated(<StrategyEditPage />) },
    { path: '*', element: <Navigate to="/" replace /> },
  ]);
}
