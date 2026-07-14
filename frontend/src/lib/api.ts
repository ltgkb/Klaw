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
