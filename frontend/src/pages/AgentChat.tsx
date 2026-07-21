import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { Bot, Send, Loader2, ArrowLeft, MessageSquare, Square } from "lucide-react"
import {
  flowApi,
  chatApi,
  type FlowRead,
  type ConversationMessage,
  type ExecutionStreamPayload,
} from "@/lib/api"
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
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const streamAbortRef = useRef<AbortController | null>(null)
  const requestSequenceRef = useRef(0)
  const selectedIdRef = useRef<string | null>(null)
  selectedIdRef.current = selectedId

  // 加载工作流列表
  useEffect(() => {
    flowApi.list().then((r) => setFlows(r.data.items)).catch(() => {})
  }, [])

  // 选中工作流时加载历史; 切换时停止上一轮执行流并复位状态。
  useEffect(() => {
    streamAbortRef.current?.abort()
    streamAbortRef.current = null
    requestSequenceRef.current += 1
    setThinking(false)
    setThinkingInfo("")
    setActiveExecutionId(null)
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
      streamAbortRef.current?.abort()
      requestSequenceRef.current += 1
    }
  }, [])

  const progressLabel = (payload: ExecutionStreamPayload) => {
    const states = Object.values(payload.node_states || {})
    const running = states.find((state) => state.status === "running")
    const completed = states.filter((state) => ["success", "skipped"].includes(state.status)).length
    if (running) return `正在执行 ${running.label || running.type || "节点"} · ${completed}/${states.length}`
    return states.length ? `执行中 · ${completed}/${states.length}` : "准备执行…"
  }

  const appendLocalReply = (content: string) => {
    setMessages((current) => [
      ...current,
      {
        id: `e-${Date.now()}`,
        role: "assistant",
        content,
        created_at: new Date().toISOString(),
      },
    ])
  }

  const loadCompletedReply = async (
    flowId: string,
    assistantCountBefore: number,
    sequence: number,
    fallback: string,
  ) => {
    for (let attempt = 0; attempt < 25; attempt += 1) {
      if (selectedIdRef.current !== flowId || requestSequenceRef.current !== sequence) return
      try {
        const response = await chatApi.messages(flowId)
        const assistantCount = response.data.filter((message) => message.role === "assistant").length
        if (assistantCount > assistantCountBefore) {
          setMessages(response.data)
          setThinking(false)
          setThinkingInfo("")
          setActiveExecutionId(null)
          return
        }
      } catch {
        // Retry briefly because the assistant message is committed after the execution terminal state.
      }
      await new Promise((resolve) => setTimeout(resolve, 200))
    }
    if (selectedIdRef.current !== flowId || requestSequenceRef.current !== sequence) return
    setThinking(false)
    setThinkingInfo("")
    setActiveExecutionId(null)
    appendLocalReply(fallback)
  }

  const finishExecution = (
    flowId: string,
    assistantCountBefore: number,
    sequence: number,
    payload: ExecutionStreamPayload,
  ) => {
    streamAbortRef.current = null
    const fallback = payload.status === "success"
      ? "(执行完成，但回答保存超时，请刷新后查看)"
      : `(${payload.error_message || (payload.status === "cancelled" ? "执行已取消" : "执行失败")})`
    void loadCompletedReply(flowId, assistantCountBefore, sequence, fallback)
  }

  const pollExecution = async (
    flowId: string,
    executionId: string,
    assistantCountBefore: number,
    sequence: number,
  ) => {
    for (let attempt = 0; attempt < 180; attempt += 1) {
      if (selectedIdRef.current !== flowId || requestSequenceRef.current !== sequence) return
      try {
        const response = await flowApi.getExecution(flowId, executionId)
        const execution = response.data
        setThinkingInfo(progressLabel({
          execution_id: execution.id,
          status: execution.status,
          node_states: execution.node_states || {},
          output: execution.output,
          error_message: execution.error_message,
        }))
        if (["success", "failed", "cancelled"].includes(execution.status)) {
          finishExecution(flowId, assistantCountBefore, sequence, {
            execution_id: execution.id,
            status: execution.status,
            node_states: execution.node_states || {},
            output: execution.output,
            error_message: execution.error_message,
          })
          return
        }
      } catch {
        // Transient API errors keep the bounded fallback poll alive.
      }
      await new Promise((resolve) => setTimeout(resolve, 1000))
    }
    if (selectedIdRef.current === flowId && requestSequenceRef.current === sequence) {
      setThinking(false)
      setActiveExecutionId(null)
      appendLocalReply("(执行状态查询超时，请在执行历史中查看)")
    }
  }

  const handleSend = async () => {
    const text = input.trim()
    if (!text || !selectedId || thinking) return
    setInput("")
    const flowId = selectedId
    const assistantCountBefore = messages.filter(
      (message) => message.role === "assistant" && !message.id.startsWith("e-"),
    ).length
    const sequence = requestSequenceRef.current + 1
    requestSequenceRef.current = sequence
    const userMsg: ConversationMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    }
    setMessages((m) => [...m, userMsg])
    setThinking(true)
    setThinkingInfo("准备执行…")

    try {
      const response = await chatApi.send(flowId, text)
      const executionId = response.data.execution_id
      setActiveExecutionId(executionId)
      streamAbortRef.current?.abort()
      streamAbortRef.current = flowApi.streamExecution(flowId, executionId, {
        onProgress: (payload) => {
          if (selectedIdRef.current === flowId && requestSequenceRef.current === sequence) {
            setThinkingInfo(progressLabel(payload))
          }
        },
        onComplete: (payload) => {
          if (selectedIdRef.current === flowId && requestSequenceRef.current === sequence) {
            finishExecution(flowId, assistantCountBefore, sequence, payload)
          }
        },
        onError: () => {
          if (selectedIdRef.current !== flowId || requestSequenceRef.current !== sequence) return
          streamAbortRef.current = null
          setThinkingInfo("实时连接中断，正在同步状态…")
          void pollExecution(flowId, executionId, assistantCountBefore, sequence)
        },
      })
    } catch {
      setThinking(false)
      setActiveExecutionId(null)
      appendLocalReply("(发送失败，请重试)")
    }
  }

  const handleCancel = async () => {
    if (!selectedId || !activeExecutionId) return
    setThinkingInfo("正在取消…")
    try {
      await flowApi.cancelExecution(selectedId, activeExecutionId)
    } catch {
      setThinkingInfo("取消失败，执行仍在继续")
    }
  }

  return (
    <div className="flex h-screen min-w-0 flex-col sm:flex-row">
      {/* 左侧: Agent 列表 */}
      <div className="max-h-40 w-full shrink-0 overflow-auto border-b bg-secondary/20 sm:max-h-none sm:h-full sm:w-60 sm:border-b-0 sm:border-r">
        <div className="border-b p-3">
          <p className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
            <Bot className="h-4 w-4" /> 选择 Agent
          </p>
          <p className="mt-0.5 text-[10px] text-muted-foreground">把工作流当聊天助手</p>
        </div>
        <div className="flex gap-1 overflow-x-auto p-2 sm:flex-col sm:overflow-x-visible">
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
                "shrink-0 rounded-md px-3 py-2 text-left text-sm transition-colors sm:w-full",
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
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {!selectedId ? (
          <div className="flex flex-1 flex-col items-center justify-center text-muted-foreground">
            <Bot className="h-12 w-12" />
            <p className="mt-4 text-sm">选择一个 Agent 开始对话</p>
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
                        "max-w-[85%] whitespace-pre-wrap break-words rounded-lg px-3 py-2 text-sm sm:max-w-[75%]",
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
                className="min-w-0 flex-1"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder="输入消息, Enter 发送"
                disabled={thinking}
              />
              <Button className="shrink-0" onClick={handleSend} disabled={thinking || !input.trim()}>
                {thinking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                发送
              </Button>
              {thinking && activeExecutionId && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCancel}
                  title="停止本次执行"
                  aria-label="停止本次执行"
                >
                  <Square className="h-4 w-4" />
                </Button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
