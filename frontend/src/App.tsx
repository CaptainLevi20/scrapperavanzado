import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { AppLayout } from "./components/layout/AppLayout";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { DashboardPage } from "./pages/DashboardPage";
import { SourcesPage } from "./pages/SourcesPage";
import { RunsPage } from "./pages/RunsPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { BulkDownloadsPage } from "./pages/BulkDownloadsPage";
import { FormatterPage } from "./pages/FormatterPage";
import { CaseLinksPage } from "./pages/CaseLinksPage";
import { CaseLinkDetailPage } from "./pages/CaseLinkDetailPage";

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
                <Route path="/casos-por-confirmar" element={<CaseLinksPage />} />
                <Route path="/casos-por-confirmar/expedientes/:caseLinkId" element={<CaseLinkDetailPage />} />
                <Route path="/formateador" element={<FormatterPage />} />
              </Route>
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
