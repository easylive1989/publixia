import { createBrowserRouter, Navigate } from 'react-router-dom';
import ScoreboardPage from './pages/ScoreboardPage';

export function createRouter() {
  return createBrowserRouter([
    { path: '/', element: <ScoreboardPage /> },
    { path: '*', element: <Navigate to="/" replace /> },
  ]);
}
