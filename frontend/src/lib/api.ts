import axios from "axios"
import { toast } from "./toast"

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

// ── 401 自动续期: access token 过期时用 refresh token 换新, 无感续登 ──
let isRefreshing = false
// 队列元素携带 retry/fail: 续期成功后 retry 重放; 续期失败逐个 fail reject, 避免请求悬挂 (Auth P2-5)
let waitQueue: Array<{ retry: () => void; fail: (err: unknown) => void }> = []

async function tryRefresh(): Promise<string | null> {
  const refreshToken = localStorage.getItem("refresh_token")
  if (!refreshToken) return null
  try {
    // 用裸 axios 调用, 绕过本拦截器避免递归
    const r = await axios.post(`${API_BASE}/auth/refresh`, { refresh_token: refreshToken })
    const { access_token, refresh_token } = r.data
    localStorage.setItem("access_token", access_token)
    localStorage.setItem("refresh_token", refresh_token)
    return access_token
  } catch {
    return null
  }
}

function forceLogout() {
  localStorage.removeItem("access_token")
  localStorage.removeItem("refresh_token")
  if (window.location.pathname !== "/login") {
    window.location.href = "/login"
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    // 401 且非 auth 接口 且未重试过 → 尝试续期
    if (
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      !String(original.url || "").includes("/auth/")
    ) {
      original._retry = true
      // 已有续期在进行中, 排队等待
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          waitQueue.push({
            retry: () => {
              original.headers.Authorization = `Bearer ${localStorage.getItem("access_token")}`
              api(original).then(resolve, reject)
            },
            fail: reject,
          })
        })
      }
      isRefreshing = true
      const newToken = await tryRefresh()
      isRefreshing = false
      if (newToken) {
        // 续期成功: 放行排队的请求 + 重试当前请求
        waitQueue.forEach((entry) => entry.retry())
        waitQueue = []
        original.headers.Authorization = `Bearer ${newToken}`
        return api(original)
      }
      // 续期失败: 逐个 reject 排队请求 (不悬挂), 再登出
      const pending = waitQueue
      waitQueue = []
      forceLogout()
      pending.forEach((entry) => entry.fail(error))
      return Promise.reject(error)
    }
    // refresh 接口本身 401 或其它 401 → 登出
    if (error.response?.status === 401) {
      forceLogout()
      return Promise.reject(error)
    }
    // 非 401 错误统一 toast 提示 (FE P1-3); /auth/ 接口由登录/注册页自行展示, 不重复提示
    if (!String(original?.url || "").includes("/auth/")) {
      const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
      const message =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d: { msg?: string }) => d?.msg ?? String(d)).join("；")
            : error.response
              ? `请求失败 (${error.response.status})`
              : "网络错误，请检查后端服务是否可用"
      toast.error(message)
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
  /** Cross-Encoder 重排序分数 (rerank=true 时后端填充) */
  rerank_score?: number | null
}

export interface SearchResponse {
  query: string
  total: number
  hits: SearchHit[]
}

export interface ChunkRead {
  id: string
  doc_id: string
  kb_id: string
  content: string
  content_type: string
  page: number
  embedding_stored: boolean
  created_at: string
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

  // Chunk 查询 (契约4)
  listChunks: (kbId: string, page = 1, pageSize = 10) =>
    api.get<PageResponse<ChunkRead>>(`/knowledge-bases/${kbId}/chunks`, {
      params: { page, page_size: pageSize },
    }),

  // 检索
  search: (kbId: string, data: { query: string; top_k?: number; threshold?: number; rerank?: boolean }) =>
    api.post<SearchResponse>(`/knowledge-bases/${kbId}/search`, data),
}

// ── Agent 工作流 API ──

export type FlowStatus = "draft" | "active" | "archived"
export type TriggerType = "manual" | "scheduled" | "webhook"
export type ExecutionStatus = "pending" | "running" | "paused" | "success" | "failed" | "cancelled"

/** XYFlow 节点类型 */
export type NodeType = "start" | "end" | "llm" | "retrieval" | "condition" | "loop" | "text" | "notify" | "memory" | "http" | "tool"

/** XYFlow 兼容的 DAG 格式 */
export interface FlowDag {
  nodes: FlowNode[]
  edges: FlowEdge[]
}

export interface FlowNode {
  id: string
  type: NodeType
  position: { x: number; y: number }
  style?: { width?: number | string; height?: number | string }
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
  status: "running" | "success" | "failed" | "skipped" | "cancelled"
  output?: string
  error?: string
  started_at?: string
  ended_at?: string
  label?: string
  type?: string
  duration_ms?: number
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

export interface ExecutionStreamPayload {
  execution_id: string
  status: ExecutionStatus
  node_states: Record<string, NodeState>
  output: Record<string, unknown> | null
  error_message: string | null
}

export interface ExecutionStreamHandlers {
  onProgress?: (payload: ExecutionStreamPayload) => void
  onComplete?: (payload: ExecutionStreamPayload) => void
  onError?: (error: Error) => void
}

function dispatchSseBlock(block: string, handlers: ExecutionStreamHandlers) {
  let event = "message"
  const data: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue
    const separator = line.indexOf(":")
    const field = separator === -1 ? line : line.slice(0, separator)
    const value = separator === -1 ? "" : line.slice(separator + 1).replace(/^ /, "")
    if (field === "event") event = value
    if (field === "data") data.push(value)
  }
  if (!data.length) return

  const raw = data.join("\n")
  if (event === "error") {
    try {
      const payload = JSON.parse(raw) as { error?: string }
      handlers.onError?.(new Error(payload.error || "执行流返回错误"))
    } catch {
      handlers.onError?.(new Error(raw || "执行流返回错误"))
    }
    return
  }

  const payload = JSON.parse(raw) as ExecutionStreamPayload
  if (event === "progress") handlers.onProgress?.(payload)
  if (event === "complete") handlers.onComplete?.(payload)
}

async function consumeExecutionStream(
  flowId: string,
  executionId: string,
  signal: AbortSignal,
  handlers: ExecutionStreamHandlers,
) {
  const url = `${API_BASE}/agent-flows/${flowId}/executions/${executionId}/stream`
  const request = (token: string | null) => fetch(url, {
    headers: {
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal,
  })

  let response = await request(localStorage.getItem("access_token"))
  if (response.status === 401) {
    const refreshed = await tryRefresh()
    if (!refreshed) {
      forceLogout()
      throw new Error("登录已过期")
    }
    response = await request(refreshed)
  }
  if (!response.ok) {
    let detail = `执行流连接失败 (${response.status})`
    try {
      const body = await response.json() as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // Keep the status-based error when the response is not JSON.
    }
    throw new Error(detail)
  }
  if (!response.body) throw new Error("浏览器不支持流式响应")

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    let boundary = buffer.match(/\r?\n\r?\n/)
    while (boundary?.index !== undefined) {
      const block = buffer.slice(0, boundary.index)
      buffer = buffer.slice(boundary.index + boundary[0].length)
      dispatchSseBlock(block, handlers)
      boundary = buffer.match(/\r?\n\r?\n/)
    }
    if (done) break
  }
  if (buffer.trim()) dispatchSseBlock(buffer, handlers)
}

export function streamExecution(
  flowId: string,
  executionId: string,
  handlers: ExecutionStreamHandlers,
): AbortController {
  const controller = new AbortController()
  void consumeExecutionStream(flowId, executionId, controller.signal, handlers).catch((error: unknown) => {
    if (controller.signal.aborted) return
    handlers.onError?.(error instanceof Error ? error : new Error("执行流连接失败"))
  })
  return controller
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

  streamExecution,

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
  search: (q: string, params?: { top_k?: number; session_id?: string }) =>
    api.get<MemoryRead[]>("/memories/search", { params: { q, ...params } }),
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
  send: (data: { title: string; content: string; channels: NotifyChannelConfig[]; channel_ids?: string[] }) =>
    api.post<NotifyResponse>("/notifications/send", data),
}

// ── 用户 API (API Key 管理) ──

export const userApi = {
  updateMe: (data: { name?: string; openai_api_key?: string; openclaw_config?: Record<string, unknown> }) =>
    api.put<UserRead>("/users/me", data),
}

// ── 用户管理 API (admin, 契约4) ──

export const usersApi = {
  list: () => api.get<UserRead[]>("/users"),

  /** 修改用户角色 (admin); 后端以 query param 接收 role */
  updateRole: (id: string, role: UserRead["role"]) =>
    api.put<UserRead>(`/users/${id}/role`, null, { params: { role } }),
}

// ── 系统配置 (embedding 模型 API 等, admin) ──

export interface EmbeddingConfig {
  base_url: string
  model: string
  has_key: boolean
  configured: boolean
  source: string // api / tei / hash
}

export const systemApi = {
  getEmbedding: () => api.get<EmbeddingConfig>("/system/embedding-config"),
  setEmbedding: (data: { base_url?: string; api_key?: string; model?: string }) =>
    api.put<EmbeddingConfig>("/system/embedding-config", data),
  getLlmDefault: () => api.get<{ default_model: string }>("/system/llm-config"),
  setLlmDefault: (default_model: string) =>
    api.put<{ default_model: string }>("/system/llm-config", { default_model }),
}

// ── 本地 Agent 工具 API (PRD 6.4) ──

export interface ToolInfo {
  id: string
  name: string
  description: string | null
  source: string
  parameters: Record<string, unknown> | null
  executable: boolean
}

export interface ToolCallResponse {
  tool_id: string
  success: boolean
  result: unknown
  error: string | null
  source: string
}

export interface LocalAgentHealth {
  openclaw: boolean
  hermes: boolean
  openclaw_url: string
  hermes_url: string
}

export const localAgentApi = {
  listTools: () => api.get<ToolInfo[]>("/local-agent/tools"),
  callTool: (toolId: string, parameters: Record<string, unknown>) =>
    api.post<ToolCallResponse>(`/local-agent/tools/${toolId}/call`, { parameters }),
  health: () => api.get<LocalAgentHealth>("/local-agent/health"),
}

// ── 文件工作区 API (PRD 6.7) ──

export interface WorkspaceFile {
  id: string
  filename: string
  file_size: number
  content_type: string
  created_at: string
}

export interface FileShare {
  url: string
  expires_hours: number
}

export const fileApi = {
  list: () => api.get<WorkspaceFile[]>("/files"),
  upload: (file: File) => {
    const formData = new FormData()
    formData.append("file", file)
    return api.post<WorkspaceFile>("/files", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    })
  },
  downloadUrl: (id: string) => `/api/v1/files/${id}`,
  /** 带 JWT 的 blob 下载 (直接 <a href> 不会带 Authorization 头) */
  download: (id: string) => api.get<Blob>(`/files/${id}`, { responseType: "blob" }),
  delete: (id: string) => api.delete(`/files/${id}`),
  share: (id: string) => api.get<FileShare>(`/files/${id}/share`),
}

// ── 推送渠道配置 API (PRD 6.6) ──

export type PushChannelType = "feishu" | "wechat" | "telegram" | "hermes"

export interface PushChannelRead {
  id: string
  name: string
  type: PushChannelType
  config: Record<string, string | null>
  created_at: string
}

export const pushChannelApi = {
  list: () => api.get<PushChannelRead[]>("/push/channels"),
  create: (data: {
    name: string
    type: PushChannelType
    config: { webhook_url?: string; bot_token?: string; chat_id?: string; channel?: string }
  }) => api.post<PushChannelRead>("/push/channels", data),
  delete: (id: string) => api.delete(`/push/channels/${id}`),
}

// ── 对话式 Agent API ──

export interface ConversationMessage {
  id: string
  role: "user" | "assistant"
  content: string
  created_at: string
}

export const chatApi = {
  messages: (flowId: string) => api.get<ConversationMessage[]>(`/agent-flows/${flowId}/chat/messages`),
  /** 发起一轮对话 (异步触发, 返回 execution_id; 需轮询 messages 获取回答) */
  send: (flowId: string, message: string) =>
    api.post<{ execution_id: string; conversation_id: string; status: string }>(
      `/agent-flows/${flowId}/chat`,
      { message },
    ),
}
