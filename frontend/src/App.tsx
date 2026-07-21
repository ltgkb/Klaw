import { useEffect, type ReactNode } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { useAuthStore } from "@/store/auth"
import { AppLayout } from "@/components/layout/AppLayout"
import { Login } from "@/pages/Login"
import { Register } from "@/pages/Register"
import { Dashboard } from "@/pages/Dashboard"
import { KnowledgeBase } from "@/pages/KnowledgeBase"
import { KBDetail } from "@/pages/KBDetail"
import { FlowList } from "@/pages/FlowList"
import { FlowCanvas } from "@/pages/FlowCanvas"
import { ExecutionList, ExecutionDetail } from "@/pages/ExecutionDetail"
import { Settings } from "@/pages/Settings"
import { ScheduleList } from "@/pages/ScheduleList"
import { MemoryList } from "@/pages/MemoryList"
import { AgentChat } from "@/pages/AgentChat"
import { Files } from "@/pages/Files"
import { UserManagement } from "@/pages/UserManagement"

/** 路由守卫：未登录跳转 /login */
function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, fetchMe, user } = useAuthStore()

  useEffect(() => {
    if (isAuthenticated && !user) {
      fetchMe()
    }
  }, [isAuthenticated, user, fetchMe])

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <AppLayout>
                <Dashboard />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/kb"
          element={
            <ProtectedRoute>
              <AppLayout>
                <KnowledgeBase />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/kb/:kbId"
          element={
            <ProtectedRoute>
              <AppLayout>
                <KBDetail />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/flows"
          element={
            <ProtectedRoute>
              <AppLayout>
                <FlowList />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/flows/:flowId"
          element={
            <ProtectedRoute>
              <FlowCanvas />
            </ProtectedRoute>
          }
        />
        <Route
          path="/flows/:flowId/executions"
          element={
            <ProtectedRoute>
              <AppLayout>
                <ExecutionList />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/flows/:flowId/executions/:execId"
          element={
            <ProtectedRoute>
              <AppLayout>
                <ExecutionDetail />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <AppLayout>
                <Settings />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/schedules"
          element={
            <ProtectedRoute>
              <AppLayout>
                <ScheduleList />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/memories"
          element={
            <ProtectedRoute>
              <AppLayout>
                <MemoryList />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/files"
          element={
            <ProtectedRoute>
              <AppLayout>
                <Files />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/users"
          element={
            <ProtectedRoute>
              <AppLayout>
                <UserManagement />
              </AppLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/agents"
          element={
            <ProtectedRoute>
              <AgentChat />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
