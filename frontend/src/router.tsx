import { createBrowserRouter, Navigate } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import StockDetailPage from './pages/StockDetailPage';
import FuturesDetailPage from './pages/FuturesDetailPage';

export function createRouter() {
  return createBrowserRouter([
    { path: '/', element: <DashboardPage /> },
    { path: '/stock/:code', element: <StockDetailPage /> },
    { path: '/futures/tw', element: <FuturesDetailPage /> },
    { path: '*', element: <Navigate to="/" replace /> },
  ]);
}
