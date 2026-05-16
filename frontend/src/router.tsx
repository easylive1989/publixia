import { createBrowserRouter, Navigate } from 'react-router-dom';
import { lazy, Suspense, type ReactElement } from 'react';
import DashboardPage from './pages/DashboardPage';
import FuturesDetailPage from './pages/FuturesDetailPage';

const ForeignFuturesPage = lazy(() => import('./pages/ForeignFuturesPage'));
const ForeignFlowAiPage  = lazy(() => import('./pages/ForeignFlowAiPage'));

function lazyRoute(node: ReactElement): ReactElement {
  return (
    <Suspense fallback={<div className="p-8 text-muted-foreground">載入中…</div>}>
      {node}
    </Suspense>
  );
}

export function createRouter() {
  return createBrowserRouter([
    { path: '/',                                  element: <DashboardPage /> },
    { path: '/futures/tw',                        element: <FuturesDetailPage /> },
    { path: '/futures/tw/foreign-flow',           element: lazyRoute(<ForeignFuturesPage />) },
    { path: '/futures/tw/foreign-flow/ai-report', element: lazyRoute(<ForeignFlowAiPage  />) },
    { path: '*', element: <Navigate to="/" replace /> },
  ]);
}
