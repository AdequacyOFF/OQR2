import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import useAuthStore from '../store/authStore';
import type { UserRole } from '../types';
import Spinner from '../components/common/Spinner';

// Auth pages
import LoginPage from '../pages/auth/LoginPage';
import RegisterPage from '../pages/auth/RegisterPage';

// Participant pages
import DashboardPage from '../pages/participant/DashboardPage';
import EntryQRPage from '../pages/participant/EntryQRPage';

// Admitter pages
import AdmissionPage from '../pages/admitter/AdmissionPage';

// Scanner pages
import ScansPage from '../pages/scanner/ScansPage';
import ScanDetailPage from '../pages/scanner/ScanDetailPage';
import ManualQRScoringPage from '../pages/scanner/ManualQRScoringPage';
import ScannerResultsPage from '../pages/scanner/ScannerResultsPage';

// Admin pages
import AdminDashboardPage from '../pages/admin/AdminDashboardPage';
import UsersPage from '../pages/admin/UsersPage';
import AuditLogPage from '../pages/admin/AuditLogPage';
import CompetitionsAdminPage from '../pages/admin/CompetitionsAdminPage';
import InstitutionsPage from '../pages/admin/InstitutionsPage';
import RoomsPage from '../pages/admin/RoomsPage';
import BadgeEditorPage from '../pages/admin/BadgeEditorPage';
import CompetitionStaffPage from '../pages/admin/CompetitionStaffPage';
import StaffBadgesPage from '../pages/admin/StaffBadgesPage';

// Invigilator pages
import InvigilatorPage from '../pages/invigilator/InvigilatorPage';

// Public pages
import ResultsPage from '../pages/public/ResultsPage';

// Test pages (development only)
import CameraTestPage from '../pages/test/CameraTestPage';

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: UserRole[];
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, allowedRoles }) => {
  const { isAuthenticated, user } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && user && !allowedRoles.includes(user.role)) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

const AppRouter: React.FC = () => {
  const { loadFromStorage } = useAuthStore();
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    loadFromStorage().finally(() => setInitializing(false));
  }, [loadFromStorage]);

  if (initializing) {
    return <Spinner />;
  }

  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/results/:competitionId" element={<ResultsPage />} />

        {/* Test routes (development only) */}
        <Route path="/test/camera" element={<CameraTestPage />} />

        {/* Participant routes */}
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute allowedRoles={['participant']}>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/competitions"
          element={
            <ProtectedRoute allowedRoles={['participant']}>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/registrations/:id/qr"
          element={
            <ProtectedRoute allowedRoles={['participant']}>
              <EntryQRPage />
            </ProtectedRoute>
          }
        />

        {/* Admitter routes */}
        <Route
          path="/admission"
          element={
            <ProtectedRoute allowedRoles={['admitter']}>
              <AdmissionPage />
            </ProtectedRoute>
          }
        />

        {/* Invigilator routes */}
        <Route
          path="/invigilator"
          element={
            <ProtectedRoute allowedRoles={['invigilator']}>
              <InvigilatorPage />
            </ProtectedRoute>
          }
        />

        {/* Scanner routes */}
        <Route
          path="/scans"
          element={
            <ProtectedRoute allowedRoles={['scanner', 'admin']}>
              <ScansPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/scans/:id"
          element={
            <ProtectedRoute allowedRoles={['scanner', 'admin']}>
              <ScanDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/scanner/qr-score"
          element={
            <ProtectedRoute allowedRoles={['scanner', 'admin']}>
              <ManualQRScoringPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/scanner/results"
          element={
            <ProtectedRoute allowedRoles={['scanner', 'admin']}>
              <ScannerResultsPage />
            </ProtectedRoute>
          }
        />

        {/* Admin routes */}
        <Route
          path="/admin"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AdminDashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/users"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <UsersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/audit-log"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <AuditLogPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/competitions"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <CompetitionsAdminPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/institutions"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <InstitutionsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/rooms"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <RoomsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/badge-editor/:competitionId"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <BadgeEditorPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/competitions/:id/staff"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <CompetitionStaffPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/staff-badges"
          element={
            <ProtectedRoute allowedRoles={['admin']}>
              <StaffBadgesPage />
            </ProtectedRoute>
          }
        />

        {/* Default redirect */}
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default AppRouter;
