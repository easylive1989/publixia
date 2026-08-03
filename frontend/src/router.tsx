import { createBrowserRouter, Navigate } from 'react-router-dom';
import MarketHeatPage from './pages/MarketHeatPage';

export function createRouter() {
  return createBrowserRouter([
    { path: '/', element: <MarketHeatPage /> },
    { path: '*', element: <Navigate to="/" replace /> },
  ]);
}
