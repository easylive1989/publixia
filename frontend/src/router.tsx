import { createBrowserRouter, Navigate } from 'react-router-dom';
import MarketHeatPage from './pages/MarketHeatPage';
import MethodPage from './pages/MethodPage';

export function createRouter() {
  return createBrowserRouter([
    { path: '/', element: <MarketHeatPage /> },
    { path: '/method', element: <MethodPage /> },
    { path: '*', element: <Navigate to="/" replace /> },
  ]);
}
