import axios from "axios"

const API_BASE = "/api/v1"

export const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
})

// 请求拦截器：注入 JWT
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401 跳登录
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("access_token")
      localStorage.removeItem("refresh_token")
      if (window.location.pathname !== "/login") {
        window.location.href = "/login"
      }
    }
    return Promise.reject(error)
  },
)

// ── 认证 API ──

export interface UserRead {
  id: string
  email: string
  name: string
  role: "admin" | "user" | "viewer"
  is_active: boolean
  created_at: string
  updated_at: string
  has_openai_key: boolean
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export const authApi = {
  register: (data: { email: string; name: string; password: string }) =>
    api.post<UserRead>("/auth/register", data),

  login: (data: { email: string; password: string }) =>
    api.post<TokenResponse>("/auth/login", data),

  me: () => api.get<UserRead>("/auth/me"),

  refresh: (refreshToken: string) =>
    api.post<TokenResponse>("/auth/refresh", { refresh_token: refreshToken }),
}

// ── 知识库 API ──

export interface KBRead {
  id: string
  name: string
  description: string | null
  owner_id: string
  embedding_model: string
  chunk_strategy: "semantic" | "recursive" | "fixed" | "markdown"
  chunk_size: number
  chunk_overlap: number
  document_count: number
  status: "active" | "indexing" | "error"
  created_at: string
  updated_at: string
}

export interface PageResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface DocumentRead {
  id: string
  kb_id: string
  filename: string
  file_size: number
  page_count: number
  parse_status: "pending" | "parsing" | "parsed" | "failed"
  created_at: string
  updated_at: string
}

export interface SearchHit {
  chunk_id: string
  doc_id: string
  content: string
  content_type: string
  page: number
  score: number
  metadata: Record<string, unknown>
}

export interface SearchResponse {
  query: string
  total: number
  hits: SearchHit[]
}

export const kbApi = {
  list: (page = 1, pageSize = 20) =>
    api.get<PageResponse<KBRead>>("/knowledge-bases", { params: { page, page_size: pageSize } }),

  get: (kbId: string) =>
    api.get<KBRead>(`/knowledge-bases/${kbId}`),

  create: (data: {
    name: string
    description?: string
    chunk_strategy?: string
    chunk_size?: number
    chunk_overlap?: number
  }) => api.post<KBRead>("/knowledge-bases", data),

  update: (kbId: string, data: { name?: string; description?: string }) =>
    api.put<KBRead>(`/knowledge-bases/${kbId}`, data),

  delete: (kbId: string) =>
    api.delete(`/knowledge-bases/${kbId}`),

  // 文档
  listDocuments: (kbId: string) =>
    api.get<DocumentRead[]>(`/knowledge-bases/${kbId}/documents`),

  uploadDocument: (kbId: string, file: File) => {
    const formData = new FormData()
    formData.append("file", file)
    return api.post<DocumentRead>(`/knowledge-bases/${kbId}/documents`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    })
  },

  deleteDocument: (kbId: string, docId: string) =>
    api.delete(`/knowledge-bases/${kbId}/documents/${docId}`),

  // 检索
  search: (kbId: string, data: { query: string; top_k?: number; threshold?: number }) =>
    api.post<SearchResponse>(`/knowledge-bases/${kbId}/search`, data),
}

// ── Agent 工作流 API ──

export type FlowStatus = "draft" | "active" | "archived"
export type TriggerType = "manual" | "scheduled" | "webhook"
export type ExecutionStatus = "pending" | "running" | "paused" | "success" | "failed" | "cancelled"

/** XYFlow 节点类型 */
export type NodeType = "llm" | "retrieval" | "condition" | "text" | "notify" | "memory"

/** XYFlow 兼容的 DAG 格式 */
export interface FlowDag {
  nodes: FlowNode[]
  edges: FlowEdge[]
}

export interface FlowNode {
  id: string
  type: NodeType
  position: { x: number; y: number }
  data: {
    label: string
    config: Record<string, unknown>
  }
}

export interface FlowEdge {
  id: string
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
}

export interface FlowRead {
  id: string
  name: string
  description: string | null
  owner_id: string
  dag: FlowDag
  status: FlowStatus
  trigger_type: TriggerType
  trigger_config: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface NodeState {
  status: "running" | "success" | "failed"
  output?: string
  error?: string
  started_at?: string
  ended_at?: string
  label?: string
  type?: string
}

export interface ExecutionRead {
  id: string
  flow_id: string
  status: ExecutionStatus
  input: Record<string, unknown> | null
  output: Record<string, unknown> | null
  node_states: Record<string, NodeState> | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface ExecuteResponse {
  execution_id: string
  flow_id: string
  status: ExecutionStatus
  message: string
}

export const flowApi = {
  list: (page = 1, pageSize = 20) =>
    api.get<PageResponse<FlowRead>>("/agent-flows", { params: { page, page_size: pageSize } }),

  get: (flowId: string) =>
    api.get<FlowRead>(`/agent-flows/${flowId}`),

  create: (data: { name: string; description?: string }) =>
    api.post<FlowRead>("/agent-flows", data),

  update: (flowId: string, data: {
    name?: string
    description?: string
    dag?: FlowDag
    status?: FlowStatus
  }) => api.put<FlowRead>(`/agent-flows/${flowId}`, data),

  delete: (flowId: string) =>
    api.delete(`/agent-flows/${flowId}`),

  // 执行
  execute: (flowId: string, input?: Record<string, unknown>) =>
    api.post<ExecuteResponse>(`/agent-flows/${flowId}/execute`, { input: input ?? {} }),

  listExecutions: (flowId: string) =>
    api.get<ExecutionRead[]>(`/agent-flows/${flowId}/executions`),

  getExecution: (flowId: string, executionId: string) =>
    api.get<ExecutionRead>(`/agent-flows/${flowId}/executions/${executionId}`),

  // 执行控制 (M4: 暂停/恢复/取消)
  pauseExecution: (flowId: string, executionId: string) =>
    api.post<ExecutionRead>(`/agent-flows/${flowId}/executions/${executionId}/pause`),

  resumeExecution: (flowId: string, executionId: string) =>
    api.post<ExecutionRead>(`/agent-flows/${flowId}/executions/${executionId}/resume`),

  cancelExecution: (flowId: string, executionId: string) =>
    api.post<ExecutionRead>(`/agent-flows/${flowId}/executions/${executionId}/cancel`),
}

// ── 模型供应商 API (M4) ──

export interface ProviderInfo {
  name: string
  status: string
  deploy: string
  priority: string
  detail: string | null
}

export interface ModelInfo {
  id: string
  provider: string
  name: string
}

export interface ChatMessage {
  role: "system" | "user" | "assistant"
  content: string
}

export interface ChatResponse {
  content: string
  model: string
  provider: string
}

export const providerApi = {
  list: () => api.get<ProviderInfo[]>("/providers"),
  listModels: () => api.get<ModelInfo[]>("/providers/models"),
  chat: (data: { messages: ChatMessage[]; model?: string; temperature?: number; max_tokens?: number }) =>
    api.post<ChatResponse>("/providers/chat", data),
}

// ── 记忆系统 API (M4) ──

export type MemoryType = "preference" | "decision" | "context"

export interface MemoryRead {
  id: string
  user_id: string
  type: MemoryType
  key: string
  value: Record<string, unknown>
  session_id: string | null
  created_at: string
  updated_at: string
}

export const memoryApi = {
  list: (params?: { type?: MemoryType; session_id?: string }) =>
    api.get<MemoryRead[]>("/memories", { params }),
  get: (id: string) => api.get<MemoryRead>(`/memories/${id}`),
  create: (data: { type?: MemoryType; key: string; value: Record<string, unknown>; session_id?: string }) =>
    api.post<MemoryRead>("/memories", data),
  update: (id: string, data: { value: Record<string, unknown> }) =>
    api.put<MemoryRead>(`/memories/${id}`, data),
  delete: (id: string) => api.delete(`/memories/${id}`),
  search: (query: string) =>
    api.get<MemoryRead[]>("/memories/search", { data: { query } }),
}

// ── 定时任务 API (M4) ──

export type ScheduleStatus = "active" | "paused"

export interface ScheduleRead {
  id: string
  flow_id: string
  name: string
  cron: string
  input: Record<string, unknown> | null
  status: ScheduleStatus
  next_run_time: string | null
  apscheduler_job_id: string | null
  created_at: string
  updated_at: string
}

export const scheduleApi = {
  list: () => api.get<ScheduleRead[]>("/schedules"),
  get: (id: string) => api.get<ScheduleRead>(`/schedules/${id}`),
  create: (data: { flow_id: string; name: string; cron: string; input?: Record<string, unknown> | null }) =>
    api.post<ScheduleRead>("/schedules", data),
  update: (id: string, data: { name?: string; cron?: string; status?: ScheduleStatus; input?: Record<string, unknown> | null }) =>
    api.put<ScheduleRead>(`/schedules/${id}`, data),
  delete: (id: string) => api.delete(`/schedules/${id}`),
}

// ── 推送通知 API (M4) ──

export interface NotifyChannelConfig {
  type: "feishu" | "wechat" | "telegram" | "hermes"
  webhook_url?: string | null
  bot_token?: string | null
  chat_id?: string | null
  channel?: string | null
}

export interface NotifyResult {
  channel: string
  success: boolean
  error: string | null
}

export interface NotifyResponse {
  results: NotifyResult[]
}

export const notifyApi = {
  send: (data: { title: string; content: string; channels: NotifyChannelConfig[] }) =>
    api.post<NotifyResponse>("/notifications/send", data),
}
