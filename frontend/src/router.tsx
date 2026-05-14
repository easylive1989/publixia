import { createBrowserRouter, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import DashboardPage from './pages/DashboardPage';
import FuturesDetailPage from './pages/FuturesDetailPage';

const ForeignFuturesPage = lazy(() => import('./pages/ForeignFuturesPage'));

export function createRouter() {
  return createBrowserRouter([
    { path: '/', element: <DashboardPage /> },
    { path: '/futures/tw', element: <FuturesDetailPage /> },
    {
      path: '/futures/tw/foreign-flow',
      element: (
        <Suspense fallback={<div className="p-8 text-muted-foreground">載入中…</div>}>
          <ForeignFuturesPage />
        </Suspense>
      ),
    },
    { path: '*', element: <Navigate to="/" replace /> },
  ]);
}
