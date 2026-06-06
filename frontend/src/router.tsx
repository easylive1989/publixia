import { createBrowserRouter, Navigate } from 'react-router-dom';
import ScoreboardPage from './pages/ScoreboardPage';
import TimelinePage from './pages/TimelinePage';

export function createRouter() {
  return createBrowserRouter([
    { path: '/',         element: <ScoreboardPage /> },
    { path: '/timeline', element: <TimelinePage /> },
    { path: '*', element: <Navigate to="/" replace /> },
  ]);
}
