import { createBrowserRouter, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import DashboardPage from './pages/DashboardPage';
import StockDetailPage from './pages/StockDetailPage';
import FuturesDetailPage from './pages/FuturesDetailPage';
import { ForeignFuturesPermissionGate } from './components/foreign-futures/PermissionGate';

const ForeignFuturesPage = lazy(() => import('./pages/ForeignFuturesPage'));

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
    { path: '*', element: <Navigate to="/" replace /> },
  ]);
}
