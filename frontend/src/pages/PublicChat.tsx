import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { ArrowUp, BookOpen, Loader2, Moon, RotateCcw, Search, Sun } from "lucide-react"

import { Button } from "@/components/ui/button"
import { publicChatApi } from "@/lib/api"
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
  const [estimatedMs, setEstimatedMs] = useState(32000)
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
    document.documentElement.dataset.colorMode = darkMode ? "dark" : "light"
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
    const currentEstimatedMs = 32000 + Math.floor(Math.random() * 100) * 10
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
        "kai-public-shell relative flex min-h-[100dvh] flex-col overflow-hidden",
        darkMode && "is-dark",
      )}
    >
      <header className="kai-public-header relative z-10 flex h-16 shrink-0 items-center justify-between px-4 sm:px-6">
        <div className="text-sm font-semibold tracking-[-0.02em]">{copy.brand}</div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={reset}
              className="kai-control"
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
            className="kai-control h-9 bg-transparent px-2 text-xs outline-none"
          >
            <option value="zh-TW">繁體中文</option>
            <option value="en">English</option>
            <option value="zh-CN">简体中文</option>
          </select>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setDarkMode((current) => !current)}
            className="kai-control"
            aria-label={darkMode ? copy.switchToLight : copy.switchToDark}
            title={darkMode ? copy.lightMode : copy.darkMode}
          >
            {darkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </header>

      <main className="relative z-10 flex min-h-0 flex-1 flex-col">
        {messages.length === 0 ? (
          <div className="mx-auto flex min-h-0 w-full max-w-[760px] flex-1 flex-col justify-start px-4 pb-4 pt-5 sm:justify-center sm:px-6 sm:pb-20 sm:pt-10">
            <div className="order-2 sm:order-1">
              <h1 className="kai-hero-title">{copy.brand}</h1>
            </div>

            <div className="order-4 mt-4 w-full sm:order-2 sm:mt-8">
              <div className="kai-query-field flex items-end rounded-xl">
                <Search className="kai-muted mb-[15px] ml-4 h-4 w-4 shrink-0" aria-hidden="true" />
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
                  className="max-h-32 min-h-12 flex-1 resize-none bg-transparent px-3 py-[14px] text-left text-sm outline-none"
                />
                <Button
                  size="icon"
                  onClick={() => void send()}
                  disabled={thinking || !input.trim()}
                  className="kai-primary-action m-1 h-10 w-10 shrink-0 rounded-lg"
                  aria-label={copy.send}
                >
                  {thinking ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
                </Button>
              </div>
            </div>

            <div className="order-3 mt-auto w-full pt-4 sm:mt-4 sm:pt-0">
              <div key={suggestionPage} className="kai-suggestion-swap flex flex-col items-start gap-2">
              {copy.suggestions.slice(suggestionPage * 4, suggestionPage * 4 + 4).map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => void send(suggestion)}
                  className="kai-suggestion flex min-h-10 max-w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-xs"
                >
                  <span>{suggestion}</span>
                  <ArrowUp className="h-3 w-3 rotate-45 opacity-50" aria-hidden="true" />
                </button>
              ))}
              </div>
            </div>

            <div className="kai-announcement order-1 mb-3 h-6 w-full overflow-hidden text-xs sm:order-4 sm:mb-0 sm:mt-8 sm:h-8">
              <div className="kai-ticker">
                {[...copy.announcements, ...copy.announcements].map((announcement, index) => (
                  <span key={`${announcement}-${index}`} className="flex h-6 items-center justify-start sm:h-8">
                    {announcement}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div ref={scrollRef} className="mx-auto w-full max-w-[760px] flex-1 space-y-6 overflow-y-auto px-4 py-6 sm:px-6 sm:py-8">
            {messages.map((message) => (
              <div
                key={message.id}
                className={cn("flex gap-3", message.role === "user" && "justify-end")}
              >
                {message.role === "assistant" && (
                  <div className="kai-brand-mark flex h-8 w-8 shrink-0 items-center justify-center" aria-hidden="true">
                    K
                  </div>
                )}
                <div
                  className={cn(
                    "kai-message max-w-[85%] whitespace-pre-wrap px-4 py-3 text-sm leading-6 sm:max-w-[75%]",
                    message.role === "user"
                      ? "kai-message-user"
                      : "kai-message-assistant",
                  )}
                >
                  {message.content}
                  {message.role === "assistant" && message.elapsedMs != null && (
                    <div className="kai-message-meta mt-3 border-t pt-2 text-[11px]">
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
                <div className="kai-brand-mark flex h-8 w-8 items-center justify-center" aria-hidden="true">
                  K
                </div>
                <div className="kai-message kai-message-assistant px-4 py-3 text-sm">
                  <div className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {copy.thinking}
                  </div>
                  <div className="kai-muted mt-1 text-[11px]">
                    {copy.queryTime}：{(liveElapsedMs / 1000).toFixed(1)}s
                    <div>{copy.estimatedTime} {`${(estimatedMs / 1000).toFixed(2)}s`}</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {messages.length > 0 && <div className="relative mx-auto w-full max-w-[760px] shrink-0 px-4 pb-4 sm:px-6 sm:pb-5">
          <div className="kai-query-field flex items-end rounded-xl">
            <Search className="kai-muted mb-[15px] ml-4 h-4 w-4 shrink-0" aria-hidden="true" />
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
                className="max-h-32 min-h-12 flex-1 resize-none bg-transparent px-3 py-[14px] text-sm outline-none"
            />
            <Button
              size="icon"
              onClick={() => void send()}
              disabled={thinking || !input.trim()}
                className="kai-primary-action m-1 h-10 w-10 shrink-0 rounded-lg"
              aria-label={copy.send}
            >
              {thinking ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
            </Button>
          </div>
          <p className="kai-muted mt-2 text-center text-[11px]">
            {copy.disclaimer}
          </p>
        </div>}
      </main>

      <Link
        to="/kb"
        className={cn(
          "kai-kb-link fixed left-4 top-20 z-20 items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium sm:bottom-5 sm:left-5 sm:top-auto sm:px-4 sm:py-2.5 sm:text-sm",
          hasAssistantReply ? "flex" : "hidden sm:flex",
        )}
      >
        <BookOpen className="h-4 w-4" />
        {copy.enterKb}
      </Link>
    </div>
  )
}
