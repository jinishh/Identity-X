import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { Toaster } from 'sonner'
import { ApiProblem } from '@/api/client'
import { Layout } from '@/components/Layout'
import { TipProvider } from '@/components/ui'
import { AlertsPage } from '@/features/alerts/AlertsPage'
import { AuditPage } from '@/features/audit/AuditPage'
import { ActivatePage } from '@/features/auth/ActivatePage'
import { LoginPage } from '@/features/auth/LoginPage'
import { CasePage } from '@/features/cases/CasePage'
import { CasesPage } from '@/features/cases/CasesPage'
import { NewCasePage } from '@/features/cases/NewCasePage'
import { UploadPage } from '@/features/cases/UploadPage'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { DemoPage } from '@/features/demo/DemoPage'
import { DocumentPage } from '@/features/documents/DocumentPage'
import { InboxPage } from '@/features/inbox/InboxPage'
import { SharedPage } from '@/features/inbox/SharedPage'
import { SearchPage } from '@/features/search/SearchPage'
import { SettingsPage } from '@/features/settings/SettingsPage'
import { UsersPage } from '@/features/admin/UsersPage'
import { VerifyPage } from '@/features/verify/VerifyPage'
import { NotFound } from '@/features/NotFound'
import { AuthProvider } from '@/lib/auth'
import { ObligationsProvider } from '@/lib/obligations'

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (n, e) => !(e instanceof ApiProblem && e.status < 500) && n < 2,
      refetchOnWindowFocus: false,
      staleTime: 10_000,
    },
  },
})

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/activate', element: <ActivatePage /> },
  { path: '/verify', element: <VerifyPage /> },
  { path: '/verify/:code', element: <VerifyPage /> },
  {
    element: <ObligationsProvider><Layout /></ObligationsProvider>,
    children: [
      { path: '/', element: <DashboardPage /> },
      { path: '/cases', element: <CasesPage /> },
      { path: '/cases/new', element: <NewCasePage /> },
      { path: '/cases/:caseId', element: <CasePage /> },
      { path: '/cases/:caseId/upload', element: <UploadPage /> },
      { path: '/documents/:docId', element: <DocumentPage /> },
      { path: '/inbox', element: <InboxPage /> },
      { path: '/shared', element: <SharedPage /> },
      { path: '/search', element: <SearchPage /> },
      { path: '/audit', element: <AuditPage /> },
      { path: '/alerts', element: <AlertsPage /> },
      { path: '/admin/users', element: <UsersPage /> },
      { path: '/demo', element: <DemoPage /> },
      { path: '/settings', element: <SettingsPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
])

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <TipProvider>
          <RouterProvider router={router} />
          <Toaster position="bottom-right" richColors closeButton toastOptions={{ style: { fontFamily: 'var(--font-sans)' } }} />
        </TipProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}
