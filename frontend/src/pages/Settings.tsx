import { useEffect, useState } from "react"
import { providerApi, type ProviderInfo, type ModelInfo, type ChatResponse } from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Loader2, Send, Cpu, Cloud, Server } from "lucide-react"

type StatusMeta = { label: string; dotClass: string }

function statusMeta(status: string): StatusMeta {
  switch (status) {
    case "ok":
      return { label: "正常", dotClass: "h-2 w-2 rounded-full bg-green-500" }
    case "unavailable":
      return { label: "不可用", dotClass: "h-2 w-2 rounded-full bg-red-500" }
    case "not_configured":
      return { label: "未配置", dotClass: "h-2 w-2 rounded-full bg-muted-foreground" }
    default:
      return { label: status, dotClass: "h-2 w-2 rounded-full bg-muted-foreground" }
  }
}

type DeployMeta = { label: string; Icon: typeof Cpu }

function deployMeta(deploy: string): DeployMeta {
  switch (deploy) {
    case "local":
      return { label: "本地", Icon: Cpu }
    case "cloud":
      return { label: "云端", Icon: Cloud }
    default:
      return { label: deploy, Icon: Server }
  }
}

export function Settings() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [models, setModels] = useState<ModelInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [chatInput, setChatInput] = useState("")
  const [chatResponse, setChatResponse] = useState<ChatResponse | null>(null)
  const [chatError, setChatError] = useState<string | null>(null)
  const [chatting, setChatting] = useState(false)

  useEffect(() => {
    const fetchAll = async () => {
      setLoading(true)
      try {
        const [providersResp, modelsResp] = await Promise.all([
          providerApi.list(),
          providerApi.listModels(),
        ])
        setProviders(providersResp.data)
        setModels(modelsResp.data)
      } catch {
        // 错误由拦截器处理
      } finally {
        setLoading(false)
      }
    }
    fetchAll()
  }, [])

  const handleSend = async () => {
    const message = chatInput.trim()
    if (!message || chatting) return
    setChatting(true)
    setChatError(null)
    setChatResponse(null)
    try {
      const resp = await providerApi.chat({
        messages: [{ role: "user", content: message }],
      })
      setChatResponse(resp.data)
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "请求失败，请检查供应商状态")
    } finally {
      setChatting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">系统设置</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          模型供应商状态 · 可用模型 · 在线测试对话
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          {/* 模型供应商 */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Server className="h-5 w-5 text-muted-foreground" />
                <div>
                  <CardTitle className="text-base">模型供应商</CardTitle>
                  <CardDescription>
                    本地 OpenClaw / Hermes 为一等公民 · 云端 OpenAI / Anthropic 兜底
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {providers.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  暂无已注册的模型供应商
                </p>
              ) : (
                providers.map((p) => {
                  const sMeta = statusMeta(p.status)
                  const dMeta = deployMeta(p.deploy)
                  return (
                    <div
                      key={p.name}
                      className="flex items-center justify-between rounded-lg border p-3"
                    >
                      <div className="flex items-center gap-3">
                        <span className={sMeta.dotClass} />
                        <div>
                          <div className="text-sm font-medium">{p.name}</div>
                          <div className="text-xs text-muted-foreground">
                            {p.detail ?? sMeta.label}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center gap-1 rounded bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">
                          <dMeta.Icon className="h-3 w-3" />
                          {dMeta.label}
                        </span>
                        <span className="rounded bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
                          优先级 {p.priority}
                        </span>
                      </div>
                    </div>
                  )
                })
              )}
            </CardContent>
          </Card>

          {/* 可用模型 */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Cpu className="h-5 w-5 text-muted-foreground" />
                <div>
                  <CardTitle className="text-base">可用模型</CardTitle>
                  <CardDescription>当前已注册的模型列表</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {models.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">暂无可用模型</p>
              ) : (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {models.map((m) => (
                    <div
                      key={m.id}
                      className="flex items-center justify-between rounded-lg border p-3 text-sm"
                    >
                      <span className="font-medium">{m.name}</span>
                      <span className="text-xs text-muted-foreground">{m.provider}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* 测试对话 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">测试对话</CardTitle>
          <CardDescription>向默认模型供应商发送一条消息，验证连通性与响应</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="chat-input">消息内容</Label>
            <div className="flex gap-2">
              <Input
                id="chat-input"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="输入测试消息，例如：你好"
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                disabled={chatting}
              />
              <Button onClick={handleSend} disabled={chatting || !chatInput.trim()}>
                {chatting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                发送
              </Button>
            </div>
          </div>

          {chatError && (
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              {chatError}
            </div>
          )}

          {chatResponse && (
            <div className="rounded-lg border bg-muted/30 p-3">
              <div className="whitespace-pre-wrap break-words text-sm">
                {chatResponse.content}
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                由 {chatResponse.provider} / {chatResponse.model} 响应
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
