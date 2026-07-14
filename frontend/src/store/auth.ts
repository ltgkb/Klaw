import { create } from "zustand"
import { authApi, type UserRead } from "@/lib/api"

interface AuthState {
  user: UserRead | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, name: string, password: string) => Promise<void>
  logout: () => void
  fetchMe: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isLoading: false,
  isAuthenticated: !!localStorage.getItem("access_token"),

  login: async (email, password) => {
    const { data } = await authApi.login({ email, password })
    localStorage.setItem("access_token", data.access_token)
    localStorage.setItem("refresh_token", data.refresh_token)
    set({ isAuthenticated: true })
    await useAuthStore.getState().fetchMe()
  },

  register: async (email, name, password) => {
    await authApi.register({ email, name, password })
    // 注册成功后自动登录
    await useAuthStore.getState().login(email, password)
  },

  logout: () => {
    localStorage.removeItem("access_token")
    localStorage.removeItem("refresh_token")
    set({ user: null, isAuthenticated: false })
  },

  fetchMe: async () => {
    try {
      const { data } = await authApi.me()
      set({ user: data, isAuthenticated: true })
    } catch {
      set({ user: null, isAuthenticated: false })
    }
  },
}))
