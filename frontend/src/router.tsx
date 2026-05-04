import { createBrowserRouter, Navigate } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import StockDetailPage from './pages/StockDetailPage';

export function createRouter() {
  return createBrowserRouter([
    { path: '/', element: <DashboardPage /> },
    { path: '/stock/:code', element: <StockDetailPage /> },
    { path: '*', element: <Navigate to="/" replace /> },
  ]);
}
