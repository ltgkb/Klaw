import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { ArrowUp, BookOpen, Loader2, Moon, RotateCcw, Sparkles, Sun } from "lucide-react"

import { Button } from "@/components/ui/button"
import { publicChatApi } from "@/lib/api"
import { PixelBrand } from "@/components/PixelBrand"
import { cn } from "@/lib/utils"

type ChatMessage = {
  id: string
  role: "user" | "assistant"
  content: string
  elapsedMs?: number
  estimatedMs?: number
}

type Locale = "zh-TW" | "en" | "zh-CN"

const CONVERSATION_KEY = "kai_public_conversation_id"
const LOCALE_KEY = "kai_public_locale"

const translations = {
  "zh-TW": {
    brand: "KAI知識",
    newChat: "新對話",
    placeholder: "請輸入你想瞭解的問題…",
    send: "傳送",
    thinking: "正在檢索知識庫並生成回答…",
    error: "暫時無法回答，請稍後重試。",
    disclaimer: "回答由AI生成，請以平台正式文件與公告為準",
    enterKb: "進入知識庫",
    lightMode: "白天模式",
    darkMode: "黑夜模式",
    switchToLight: "切換到白天模式",
    switchToDark: "切換到黑夜模式",
    language: "語言",
    queryTime: "查詢時間",
    estimatedTime: "預計啟用深度檢索輸出需要",
    fasterThanEstimated: "比預計快了",
    withinEstimated: "本次用時符合預計",
    suggestions: [
      "什麼是期算平台？",
      "平台如何完成交易與結算？",
      "如何成為平台參與方？",
      "平台提供哪些風險控制機制？",
      "供應商如何申請准入？",
      "採購方如何進入平台？",
      "服務商承擔哪些責任？",
      "平台如何進行實物交割？",
      "保證金規則是什麼？",
      "訂單如何撮合成交？",
      "如何處理交付違約？",
      "平台如何完成清算？",
    ],
    announcements: [
      "KAI知識公開問答已上線",
      "參與方問題支援供應商、採購方與服務商聯合檢索",
      "回答內容請以平台正式文件與公告為準",
    ],
  },
  en: {
    brand: "KAI Knowledge",
    newChat: "New chat",
    placeholder: "Ask anything about KAI…",
    send: "Send",
    thinking: "Searching the knowledge base and preparing an answer…",
    error: "Unable to answer right now. Please try again later.",
    disclaimer: "AI-generated answers are subject to official platform documents and notices",
    enterKb: "Knowledge Base",
    lightMode: "Light mode",
    darkMode: "Dark mode",
    switchToLight: "Switch to light mode",
    switchToDark: "Switch to dark mode",
    language: "Language",
    queryTime: "Query time",
    estimatedTime: "Estimated deep-search response time",
    fasterThanEstimated: "Faster than estimated by",
    withinEstimated: "Completed within the estimated time",
    suggestions: [
      "What is the KAI futures computing platform?",
      "How are trades and settlements completed?",
      "How can I become a platform participant?",
      "What risk controls does the platform provide?",
      "How does a supplier apply for admission?",
      "How can a buyer join the platform?",
      "What responsibilities does a service provider have?",
      "How does physical delivery work?",
      "What are the margin rules?",
      "How are orders matched?",
      "How are delivery defaults handled?",
      "How does platform clearing work?",
    ],
    announcements: [
      "KAI Knowledge public Q&A is now live",
      "Participant queries search supplier, buyer, and service-provider sources",
      "Please refer to official platform documents and notices",
    ],
  },
  "zh-CN": {
    brand: "KAI知识",
    newChat: "新对话",
    placeholder: "请输入你想了解的问题…",
    send: "发送",
    thinking: "正在检索知识库并生成回答…",
    error: "暂时无法回答，请稍后重试。",
    disclaimer: "回答由AI生成，请以平台正式文件与公告为准",
    enterKb: "进入知识库",
    lightMode: "白天模式",
    darkMode: "黑夜模式",
    switchToLight: "切换到白天模式",
    switchToDark: "切换到黑夜模式",
    language: "语言",
    queryTime: "查询时间",
    estimatedTime: "预计启用深度检索输出需要",
    fasterThanEstimated: "比预计快了",
    withinEstimated: "本次用时符合预计",
    suggestions: [
      "什么是期算平台？",
      "平台如何完成交易与结算？",
      "如何成为平台参与方？",
      "平台提供哪些风险控制机制？",
      "供应商如何申请准入？",
      "采购方如何进入平台？",
      "服务商承担哪些责任？",
      "平台如何进行实物交割？",
      "保证金规则是什么？",
      "订单如何撮合成交？",
      "如何处理交付违约？",
      "平台如何完成清算？",
    ],
    announcements: [
      "KAI知识公开问答已上线",
      "参与方问题支持供应商、采购方与服务商联合检索",
      "回答内容请以平台正式文件与公告为准",
    ],
  },
} satisfies Record<Locale, {
  brand: string
  newChat: string
  placeholder: string
  send: string
  thinking: string
  error: string
  disclaimer: string
  enterKb: string
  lightMode: string
  darkMode: string
  switchToLight: string
  switchToDark: string
  language: string
  queryTime: string
  estimatedTime: string
  fasterThanEstimated: string
  withinEstimated: string
  suggestions: string[]
  announcements: string[]
}>

export function PublicChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [thinking, setThinking] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [liveElapsedMs, setLiveElapsedMs] = useState(0)
  const [estimatedMs, setEstimatedMs] = useState(50000)
  const [suggestionPage, setSuggestionPage] = useState(0)
  const [locale, setLocale] = useState<Locale>(() => {
    const saved = localStorage.getItem(LOCALE_KEY)
    return saved === "zh-TW" || saved === "en" || saved === "zh-CN" ? saved : "zh-TW"
  })
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem("kai_public_theme")
    if (saved) return saved === "dark"
    return window.matchMedia("(prefers-color-scheme: dark)").matches
  })
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const queryStartedAtRef = useRef<number | null>(null)
  const copy = translations[locale]
  const hasAssistantReply = messages.some((message) => message.role === "assistant")

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    })
  }, [messages, thinking])

  useEffect(() => {
    localStorage.setItem("kai_public_theme", darkMode ? "dark" : "light")
  }, [darkMode])

  useEffect(() => {
    localStorage.setItem(LOCALE_KEY, locale)
    document.documentElement.lang = locale
    document.title = copy.brand
    setSuggestionPage(0)
  }, [locale, copy.brand])

  useEffect(() => {
    const timer = window.setInterval(() => {
      setSuggestionPage((current) => (current + 1) % 3)
    }, 3333)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!thinking || streaming || queryStartedAtRef.current == null) return
    const timer = window.setInterval(() => {
      if (queryStartedAtRef.current != null) {
        setLiveElapsedMs(performance.now() - queryStartedAtRef.current)
      }
    }, 100)
    return () => window.clearInterval(timer)
  }, [thinking, streaming])

  const send = async (preset?: string) => {
    const text = (preset ?? input).trim()
    if (!text || thinking) return
    setInput("")
    setMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: "user", content: text },
    ])
    const startedAt = performance.now()
    const currentEstimatedMs = 50000 + Math.floor(Math.random() * 100) * 10
    queryStartedAtRef.current = startedAt
    setLiveElapsedMs(0)
    setEstimatedMs(currentEstimatedMs)
    setThinking(true)
    try {
      const conversationId = sessionStorage.getItem(CONVERSATION_KEY)
      const response = await publicChatApi.send(text, conversationId, locale)
      sessionStorage.setItem(CONVERSATION_KEY, response.data.conversation_id)
      const elapsedMs = performance.now() - startedAt
      queryStartedAtRef.current = null
      setLiveElapsedMs(elapsedMs)
      setStreaming(true)
      const assistantId = `assistant-${response.data.execution_id}`
      setMessages((current) => [
        ...current,
        {
          id: assistantId,
          role: "assistant",
          content: "",
          elapsedMs,
          estimatedMs: currentEstimatedMs,
        },
      ])
      const characters = Array.from(response.data.answer)
      for (let end = 8; end < characters.length + 8; end += 8) {
        const content = characters.slice(0, end).join("")
        setMessages((current) =>
          current.map((message) => message.id === assistantId ? { ...message, content } : message),
        )
        await new Promise((resolve) => window.setTimeout(resolve, 24))
      }
    } catch {
      const elapsedMs = performance.now() - startedAt
      queryStartedAtRef.current = null
      setLiveElapsedMs(elapsedMs)
      setMessages((current) => [
        ...current,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: copy.error,
          elapsedMs,
          estimatedMs: currentEstimatedMs,
        },
      ])
    } finally {
      queryStartedAtRef.current = null
      setStreaming(false)
      setThinking(false)
    }
  }

  const reset = () => {
    sessionStorage.removeItem(CONVERSATION_KEY)
    setMessages([])
    setInput("")
    setLiveElapsedMs(0)
    setStreaming(false)
    setThinking(false)
    queryStartedAtRef.current = null
  }

  return (
    <div
      className={cn(
        "relative flex min-h-[100dvh] flex-col overflow-hidden transition-colors duration-500",
        darkMode ? "bg-[#0a0c11] text-slate-100" : "bg-[#f7f8fb] text-slate-900",
      )}
    >
      <div className={cn("kai-tech-grid pointer-events-none absolute inset-0", darkMode && "kai-tech-grid-dark")} />
      <div
        className={cn(
          "pointer-events-none absolute left-1/2 top-1/3 h-[32rem] w-[32rem] -translate-x-1/2 rounded-full blur-3xl transition-colors duration-500",
          darkMode ? "bg-indigo-500/[0.07]" : "bg-blue-300/15",
        )}
      />

      <header
        className={cn(
          "relative z-10 flex h-16 shrink-0 items-center justify-between px-5 backdrop-blur-xl transition-colors sm:px-8",
          darkMode ? "bg-[#0a0c11]/75" : "border-b border-white/80 bg-white/70",
        )}
      >
        <div className="flex items-center gap-3">
          <div className={cn(
            "flex h-9 w-9 items-center justify-center rounded-xl text-white shadow-sm",
            darkMode ? "bg-white/[0.06] text-blue-300" : "bg-slate-950",
          )}>
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <div className="text-sm font-semibold tracking-tight">{copy.brand}</div>
            <div className={cn("text-[11px]", darkMode ? "text-slate-500" : "text-slate-500")}>
              Knowledge Intelligence
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={reset}
              className={darkMode ? "text-slate-400 hover:bg-white/5 hover:text-white" : "text-slate-500"}
            >
              <RotateCcw className="h-4 w-4" />
              {copy.newChat}
            </Button>
          )}
          <select
            value={locale}
            onChange={(event) => setLocale(event.target.value as Locale)}
            aria-label={copy.language}
            title={copy.language}
            className={cn(
              "h-9 rounded-xl bg-transparent px-2 text-xs outline-none",
              darkMode
                ? "text-slate-400 hover:bg-white/[0.06] hover:text-white"
                : "text-slate-500 hover:bg-slate-100",
            )}
          >
            <option value="zh-TW">繁體中文</option>
            <option value="en">English</option>
            <option value="zh-CN">简体中文</option>
          </select>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setDarkMode((current) => !current)}
            className={cn(
              "rounded-xl",
              darkMode ? "text-slate-400 hover:bg-white/[0.06] hover:text-white" : "text-slate-500",
            )}
            aria-label={darkMode ? copy.switchToLight : copy.switchToDark}
            title={darkMode ? copy.lightMode : copy.darkMode}
          >
            {darkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </header>

      <main className="relative z-10 flex min-h-0 flex-1 flex-col">
        {messages.length === 0 ? (
          <div className="mx-auto flex min-h-0 w-full max-w-4xl flex-1 flex-col items-center justify-start px-4 pb-4 pt-6 text-center sm:justify-center sm:px-5 sm:pb-20 sm:pt-10">
            <h1 className="order-2 w-full sm:order-1">
              <span className="sr-only">{copy.brand}</span>
              <PixelBrand text={copy.brand} darkMode={darkMode} />
            </h1>

            <div className="order-4 mt-4 w-full max-w-2xl sm:order-2 sm:mt-10">
              <div className={cn(
                "flex items-end gap-2 rounded-2xl p-2 backdrop-blur-xl transition-colors",
                darkMode
                  ? "bg-[#141821]/90 shadow-[0_18px_70px_rgba(0,0,0,0.38)]"
                  : "border border-slate-200/80 bg-white/80 shadow-[0_16px_50px_rgba(15,23,42,0.08)]",
              )}>
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault()
                      void send()
                    }
                  }}
                  rows={1}
                  placeholder={copy.placeholder}
                  disabled={thinking}
                  className={cn(
                    "max-h-32 min-h-11 flex-1 resize-none bg-transparent px-3 py-3 text-left text-sm outline-none",
                    darkMode ? "text-slate-100 placeholder:text-slate-600" : "placeholder:text-slate-400",
                  )}
                />
                <Button
                  size="icon"
                  onClick={() => void send()}
                  disabled={thinking || !input.trim()}
                  className={cn(
                    "h-11 w-11 shrink-0 rounded-xl",
                    darkMode ? "bg-white text-slate-950 hover:bg-slate-200" : "bg-slate-950 hover:bg-slate-800",
                  )}
                  aria-label={copy.send}
                >
                  {thinking ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
                </Button>
              </div>
            </div>

            <div className="order-3 mt-auto w-full max-w-2xl pt-4 sm:mt-4 sm:pt-0">
              <div key={suggestionPage} className="kai-suggestion-swap flex flex-col items-start gap-2">
              {copy.suggestions.slice(suggestionPage * 4, suggestionPage * 4 + 4).map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => void send(suggestion)}
                  style={{ width: "fit-content", maxWidth: "100%" }}
                  className={cn(
                    "rounded-xl px-4 py-2.5 text-left text-xs backdrop-blur transition",
                    darkMode
                      ? "bg-[#121620]/90 text-slate-300 hover:bg-[#191e2a] hover:text-white"
                      : "border border-slate-200/80 bg-white/55 text-slate-500 hover:border-slate-300 hover:bg-white hover:text-slate-900",
                  )}
                >
                  {suggestion}
                </button>
              ))}
              </div>
            </div>

            <div className={cn(
              "order-1 mb-3 h-6 w-full max-w-2xl overflow-hidden text-xs sm:order-4 sm:mb-0 sm:mt-10 sm:h-9",
              darkMode ? "text-slate-500" : "text-slate-400",
            )}>
              <div className="kai-ticker">
                {[...copy.announcements, ...copy.announcements].map((announcement, index) => (
                  <span key={`${announcement}-${index}`} className="flex h-6 items-center justify-start px-1 sm:h-9">
                    <span className={cn("mr-2 h-1 w-1 rounded-full", darkMode ? "bg-indigo-400/70" : "bg-slate-300")} />
                    {announcement}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div ref={scrollRef} className="mx-auto w-full max-w-4xl flex-1 space-y-6 overflow-y-auto px-5 py-8">
            {messages.map((message) => (
              <div
                key={message.id}
                className={cn("flex gap-3", message.role === "user" && "justify-end")}
              >
                {message.role === "assistant" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-950 text-white">
                    <Sparkles className="h-4 w-4" />
                  </div>
                )}
                <div
                  className={cn(
                    "max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm sm:max-w-[75%]",
                    message.role === "user"
                      ? darkMode ? "bg-white text-slate-950" : "bg-slate-950 text-white"
                      : darkMode
                        ? "bg-[#141821]/90 text-slate-200"
                        : "border border-white bg-white/85 text-slate-700",
                  )}
                >
                  {message.content}
                  {message.role === "assistant" && message.elapsedMs != null && (
                    <div className={cn(
                      "mt-2 border-t pt-1.5 text-[11px]",
                      darkMode ? "border-white/[0.06] text-slate-500" : "border-slate-100 text-slate-400",
                    )}>
                      {copy.queryTime}：{(message.elapsedMs / 1000).toFixed(2)}s
                      {message.estimatedMs != null && (
                        <div>
                          {message.elapsedMs < message.estimatedMs
                            ? `${copy.fasterThanEstimated} ${((message.estimatedMs - message.elapsedMs) / 1000).toFixed(2)}s`
                            : copy.withinEstimated}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {thinking && !streaming && (
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-950 text-white">
                  <Sparkles className="h-4 w-4" />
                </div>
                <div className={cn(
                  "rounded-2xl px-4 py-3 text-sm shadow-sm",
                  darkMode
                    ? "bg-[#141821]/90 text-slate-400"
                    : "border border-white bg-white/85 text-slate-500",
                )}>
                  <div className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {copy.thinking}
                  </div>
                  <div className={cn("mt-1 text-[11px]", darkMode ? "text-slate-600" : "text-slate-400")}>
                    {copy.queryTime}：{(liveElapsedMs / 1000).toFixed(1)}s
                    <div>{copy.estimatedTime} {`${(estimatedMs / 1000).toFixed(2)}s`}</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {messages.length > 0 && <div className="relative mx-auto w-full max-w-4xl shrink-0 px-5 pb-5">
          <div className={cn(
            "flex items-end gap-2 rounded-2xl p-2 backdrop-blur-xl",
            darkMode
              ? "bg-[#141821]/90 shadow-[0_18px_70px_rgba(0,0,0,0.38)]"
              : "border border-white bg-white/90 shadow-[0_16px_50px_rgba(15,23,42,0.12)]",
          )}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault()
                  void send()
                }
              }}
              rows={1}
              placeholder={copy.placeholder}
              disabled={thinking}
                className={cn(
                  "max-h-32 min-h-11 flex-1 resize-none bg-transparent px-3 py-3 text-sm outline-none",
                  darkMode ? "text-slate-100 placeholder:text-slate-600" : "placeholder:text-slate-400",
                )}
            />
            <Button
              size="icon"
              onClick={() => void send()}
              disabled={thinking || !input.trim()}
                className={cn(
                  "h-11 w-11 shrink-0 rounded-xl",
                  darkMode ? "bg-white text-slate-950 hover:bg-slate-200" : "bg-slate-950 hover:bg-slate-800",
                )}
              aria-label={copy.send}
            >
              {thinking ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
            </Button>
          </div>
          <p className={cn("mt-2 text-center text-[11px]", darkMode ? "text-slate-600" : "text-slate-400")}>
            {copy.disclaimer}
          </p>
        </div>}
      </main>

      <Link
        to="/kb"
        className={cn(
          "fixed left-4 top-20 z-20 items-center gap-2 rounded-xl px-3 py-2 text-xs font-medium shadow-lg backdrop-blur transition hover:-translate-y-0.5 sm:bottom-5 sm:left-5 sm:top-auto sm:px-4 sm:py-2.5 sm:text-sm",
          hasAssistantReply ? "flex" : "hidden sm:flex",
          darkMode
            ? "bg-[#141821]/85 text-slate-300 hover:bg-[#1a1f2a] hover:text-white"
            : "border border-slate-200 bg-white/90 text-slate-700 hover:bg-white",
        )}
      >
        <BookOpen className="h-4 w-4" />
        {copy.enterKb}
      </Link>
    </div>
  )
}
