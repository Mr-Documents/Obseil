import { Navigate, Route, Routes } from 'react-router-dom';

import { RedirectIfAuthenticated, RequireAuth } from '@/components/RequireAuth';
import { AppLayout } from '@/layouts/AppLayout';
import { LoginPage } from '@/pages/auth/LoginPage';
import { RegisterPage } from '@/pages/auth/RegisterPage';
import { DatasetAnomaliesPage } from '@/pages/datasets/DatasetAnomaliesPage';
import { DatasetColumnsPage } from '@/pages/datasets/DatasetColumnsPage';
import { DatasetHistoryPage } from '@/pages/datasets/DatasetHistoryPage';
import { DatasetFindingsPage } from '@/pages/datasets/DatasetFindingsPage';
import { DatasetLayout } from '@/pages/datasets/DatasetLayout';
import { DatasetOverviewPage } from '@/pages/datasets/DatasetOverviewPage';
import { DatasetRowsPage } from '@/pages/datasets/DatasetRowsPage';
import { LandingPage } from '@/pages/LandingPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { ProjectDetailPage } from '@/pages/projects/ProjectDetailPage';
import { ProjectHistoryPage } from '@/pages/projects/ProjectHistoryPage';
import { ProjectsPage } from '@/pages/projects/ProjectsPage';

/**
 * Route table. The public/private split is visible at a glance: everything
 * inside `<RequireAuth>` needs a session, everything outside does not.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />

      <Route
        path="/login"
        element={
          <RedirectIfAuthenticated>
            <LoginPage />
          </RedirectIfAuthenticated>
        }
      />
      <Route
        path="/register"
        element={
          <RedirectIfAuthenticated>
            <RegisterPage />
          </RedirectIfAuthenticated>
        }
      />

      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
        <Route path="/projects/:projectId/history" element={<ProjectHistoryPage />} />

        <Route path="/datasets/:datasetId" element={<DatasetLayout />}>
          <Route index element={<DatasetOverviewPage />} />
          <Route path="findings" element={<DatasetFindingsPage />} />
          <Route path="anomalies" element={<DatasetAnomaliesPage />} />
          <Route path="columns" element={<DatasetColumnsPage />} />
          <Route path="rows" element={<DatasetRowsPage />} />
          <Route path="history" element={<DatasetHistoryPage />} />
        </Route>

        <Route path="/dashboard" element={<Navigate to="/projects" replace />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
