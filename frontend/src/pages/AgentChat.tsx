import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { Bot, Send, Loader2, ArrowLeft, MessageSquare } from "lucide-react"
import { flowApi, chatApi, type FlowRead, type ConversationMessage } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

export function AgentChat() {
  const [flows, setFlows] = useState<FlowRead[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [input, setInput] = useState("")
  const [loadingMsgs, setLoadingMsgs] = useState(false)
  const [thinking, setThinking] = useState(false)
  const [thinkingInfo, setThinkingInfo] = useState<string>("")
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // 当前选中的 flowId 快照, 供轮询回调校验, 防止切换 Agent 后旧轮询串台
  const selectedIdRef = useRef<string | null>(null)
  selectedIdRef.current = selectedId

  // 加载工作流列表
  useEffect(() => {
    flowApi.list().then((r) => setFlows(r.data.items)).catch(() => {})
  }, [])

  // 选中工作流时加载历史; 切换时停止上一轮轮询并复位 thinking (P1-2)
  useEffect(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current)
      pollTimer.current = null
    }
    setThinking(false)
    setThinkingInfo("")
    setMessages([])
    if (!selectedId) return
    setLoadingMsgs(true)
    chatApi
      .messages(selectedId)
      .then((r) => setMessages(r.data))
      .catch(() => setMessages([]))
      .finally(() => setLoadingMsgs(false))
  }, [selectedId])

  // 自动滚到底
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages, thinking])

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current)
    }
  }, [])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || !selectedId || thinking) return
    setInput("")
    const flowId = selectedId
    // 记录发送前的消息数, 用于检测新助手回复
    const beforeCount = messages.length
    const userMsg: ConversationMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    }
    setMessages((m) => [...m, userMsg])
    setThinking(true)
    setThinkingInfo("执行中…")

    try {
      await chatApi.send(flowId, text)
    } catch {
      setThinking(false)
      setMessages((m) => [
        ...m,
        {
          id: `e-${Date.now()}`,
          role: "assistant",
          content: "(发送失败, 请重试)",
          created_at: new Date().toISOString(),
        },
      ])
      return
    }

    // 轮询消息, 直到出现新的助手回复 (最多 ~3 分钟)
    let attempts = 0
    const poll = async () => {
      // 已切换到其它 Agent: 停止轮询, 不写消息 (P1-2 防串台)
      if (selectedIdRef.current !== flowId) return
      attempts += 1
      try {
        const r = await chatApi.messages(flowId)
        if (selectedIdRef.current !== flowId) return
        const list = r.data
        // 持久化列表已含本次用户消息; 若又多出一条助手消息, 即为回答
        if (list.length > beforeCount + 1) {
          setMessages(list)
          setThinking(false)
          setThinkingInfo("")
          return
        }
        // 更新进度提示
        setThinkingInfo(`执行中… (${attempts}s)`)
      } catch {
        /* ignore, 继续轮询 */
      }
      if (attempts > 180) {
        setThinking(false)
        setMessages((m) => [
          ...m,
          {
            id: `e-${Date.now()}`,
            role: "assistant",
            content: "(执行超时, 请重试)",
            created_at: new Date().toISOString(),
          },
        ])
        return
      }
      pollTimer.current = setTimeout(poll, 1000)
    }
    pollTimer.current = setTimeout(poll, 1000)
  }

  return (
    <div className="flex h-screen">
      {/* 左侧: Agent 列表 */}
      <div className="w-60 shrink-0 border-r bg-secondary/20 overflow-y-auto">
        <div className="border-b p-3">
          <p className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
            <Bot className="h-4 w-4" /> 选择 Agent
          </p>
          <p className="mt-0.5 text-[10px] text-muted-foreground">把工作流当聊天助手</p>
        </div>
        <div className="flex flex-col gap-1 p-2">
          {flows.length === 0 && (
            <p className="p-3 text-xs text-muted-foreground">
              暂无工作流, <Link to="/flows" className="underline">去创建</Link>
            </p>
          )}
          {flows.map((f) => (
            <button
              key={f.id}
              onClick={() => setSelectedId(f.id)}
              className={cn(
                "rounded-md px-3 py-2 text-left text-sm transition-colors",
                selectedId === f.id ? "bg-primary/10 text-primary" : "hover:bg-muted",
              )}
            >
              <div className="flex items-center gap-2">
                <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{f.name}</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 右侧: 聊天 */}
      <div className="flex flex-1 flex-col">
        {!selectedId ? (
          <div className="flex flex-1 flex-col items-center justify-center text-muted-foreground">
            <Bot className="h-12 w-12" />
            <p className="mt-4 text-sm">从左侧选择一个 Agent 开始对话</p>
            <Link to="/flows">
              <Button variant="outline" size="sm" className="mt-4">
                <ArrowLeft className="h-4 w-4" /> 返回工作流
              </Button>
            </Link>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-2 border-b px-4 py-2">
              <Link to="/flows" title="返回工作流列表">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="h-4 w-4" />
                </Button>
              </Link>
              <div>
                <h1 className="text-sm font-semibold">
                  {flows.find((f) => f.id === selectedId)?.name}
                </h1>
                <p className="text-[11px] text-muted-foreground">
                  对话式运行 · 多轮历史作为 {`{history}`} 注入 LLM 节点
                </p>
              </div>
            </div>

            <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
              {loadingMsgs ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : (
                messages.map((m) => (
                  <div key={m.id} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                    <div
                      className={cn(
                        "max-w-[75%] whitespace-pre-wrap break-words rounded-lg px-3 py-2 text-sm",
                        m.role === "user"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-foreground",
                      )}
                    >
                      {m.content}
                    </div>
                  </div>
                ))
              )}
              {thinking && (
                <div className="flex justify-start">
                  <div className="flex items-center gap-2 rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {thinkingInfo || "思考中…"}
                  </div>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2 border-t p-3">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder="输入消息, Enter 发送"
                disabled={thinking}
              />
              <Button onClick={handleSend} disabled={thinking || !input.trim()}>
                {thinking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                发送
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
