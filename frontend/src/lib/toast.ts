/**
 * 轻量全局 toast 提示工具 (FE P1-3)。
 * 不依赖任何 UI 库, 直接挂载到 document.body, 自动消失。
 */

type ToastKind = "success" | "error" | "info"

const CONTAINER_ID = "app-toast-container"

const kindClass: Record<ToastKind, string> = {
  success: "border-green-500/50 bg-green-50 text-green-700",
  error: "border-destructive/50 bg-destructive/10 text-destructive",
  info: "border-border bg-background text-foreground",
}

function ensureContainer(): HTMLDivElement | null {
  if (typeof document === "undefined") return null
  let el = document.getElementById(CONTAINER_ID) as HTMLDivElement | null
  if (!el) {
    el = document.createElement("div")
    el.id = CONTAINER_ID
    el.className =
      "pointer-events-none fixed right-4 top-4 z-[9999] flex w-80 flex-col gap-2"
    document.body.appendChild(el)
  }
  return el
}

function show(kind: ToastKind, message: string, durationMs = 3500) {
  const container = ensureContainer()
  if (!container) return
  const el = document.createElement("div")
  el.className = `pointer-events-auto rounded-md border px-3 py-2 text-sm shadow-md transition-opacity ${kindClass[kind]}`
  el.textContent = message
  el.style.opacity = "1"
  container.appendChild(el)
  window.setTimeout(() => {
    el.style.transition = "opacity 300ms"
    el.style.opacity = "0"
    window.setTimeout(() => el.remove(), 320)
  }, durationMs)
}

export const toast = {
  success: (message: string, durationMs?: number) => show("success", message, durationMs),
  error: (message: string, durationMs?: number) => show("error", message, durationMs ?? 4500),
  info: (message: string, durationMs?: number) => show("info", message, durationMs),
}
