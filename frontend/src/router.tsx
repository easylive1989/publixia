import { createBrowserRouter, Navigate } from 'react-router-dom';
import { lazy, Suspense, type ReactElement } from 'react';
import HomePage from './pages/HomePage';

const PersonProfilePage = lazy(() => import('./pages/PersonProfilePage'));

function lazyRoute(node: ReactElement): ReactElement {
  return (
    <Suspense fallback={<div className="p-8 text-muted-foreground">載入中…</div>}>
      {node}
    </Suspense>
  );
}

export function createRouter() {
  return createBrowserRouter([
    { path: '/',                  element: <HomePage /> },
    { path: '/people/:personKey', element: lazyRoute(<PersonProfilePage />) },
    { path: '*', element: <Navigate to="/" replace /> },
  ]);
}
