import { lazy } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AdminRoute } from "./auth/AdminRoute";
import { AuthProvider } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { AppLayout } from "./components/layout/AppLayout";
// Login/Register stay eagerly imported: they're the first screen an unauthenticated
// visitor sees, so there's no code-splitting win in making them fetch an extra
// chunk before the login form can even paint.
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";

// The authenticated pages are code-split: each downloads only when its route is
// first visited, keeping the initial bundle small (Laboratorio in particular
// carries a chunky rules engine that most sessions never open). They all render
// under AppLayout's <Outlet>, whose <Suspense> boundary shows the fallback while
// a chunk loads. React.lazy needs a default export, hence the `.then` unwrap of
// each page's named export.
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const SourcesPage = lazy(() => import("./pages/SourcesPage").then((m) => ({ default: m.SourcesPage })));
const RunsPage = lazy(() => import("./pages/RunsPage").then((m) => ({ default: m.RunsPage })));
const RunDetailPage = lazy(() => import("./pages/RunDetailPage").then((m) => ({ default: m.RunDetailPage })));
const DocumentsPage = lazy(() => import("./pages/DocumentsPage").then((m) => ({ default: m.DocumentsPage })));
const BulkDownloadsPage = lazy(() => import("./pages/BulkDownloadsPage").then((m) => ({ default: m.BulkDownloadsPage })));
const FormatterPage = lazy(() => import("./pages/FormatterPage").then((m) => ({ default: m.FormatterPage })));
const ExpedientesPage = lazy(() => import("./pages/ExpedientesPage").then((m) => ({ default: m.ExpedientesPage })));
const CaseLinkDetailPage = lazy(() =>
  import("./pages/CaseLinkDetailPage").then((m) => ({ default: m.CaseLinkDetailPage }))
);

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<AppLayout />}>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/sources" element={<SourcesPage />} />
                <Route path="/runs" element={<RunsPage />} />
                <Route path="/runs/:runId" element={<RunDetailPage />} />
                <Route path="/documents" element={<DocumentsPage />} />
                <Route path="/bulk-downloads" element={<BulkDownloadsPage />} />
                <Route path="/expedientes" element={<ExpedientesPage />} />
                <Route path="/expedientes/:caseLinkId" element={<CaseLinkDetailPage />} />
                <Route element={<AdminRoute />}>
                  <Route path="/laboratorio" element={<FormatterPage />} />
                </Route>
              </Route>
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
