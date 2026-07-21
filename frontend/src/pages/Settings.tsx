import { useEffect, useState } from "react"
import {
  providerApi,
  userApi,
  localAgentApi,
  pushChannelApi,
  systemApi,
  notifyApi,
  type ProviderInfo,
  type ModelInfo,
  type ChatResponse,
  type ToolInfo,
  type PushChannelRead,
  type PushChannelType,
  type EmbeddingConfig,
  type LocalAgentHealth,
} from "@/lib/api"
import { toast } from "@/lib/toast"
import { useAuthStore } from "@/store/auth"
import { cn } from "@/lib/utils"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Loader2, Send, Cpu, Cloud, Server, KeyRound, Trash2, Wrench, Plus, Zap } from "lucide-react"

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

const CHANNEL_TYPES: { value: PushChannelType; label: string; hint: string }[] = [
  { value: "feishu", label: "飞书", hint: "webhook_url" },
  { value: "wechat", label: "企业微信", hint: "webhook_url" },
  { value: "telegram", label: "Telegram", hint: "bot_token + chat_id" },
  { value: "hermes", label: "Hermes", hint: "channel" },
]

export function Settings() {
  const { user, fetchMe } = useAuthStore()
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [models, setModels] = useState<ModelInfo[]>([])
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [chatInput, setChatInput] = useState("")
  const [chatModel, setChatModel] = useState("default")
  const [chatResponse, setChatResponse] = useState<ChatResponse | null>(null)
  const [chatError, setChatError] = useState<string | null>(null)
  const [chatting, setChatting] = useState(false)

  // API Key
  const [openaiKey, setOpenaiKey] = useState("")
  const [keySaving, setKeySaving] = useState(false)
  const [keyMsg, setKeyMsg] = useState<string | null>(null)

  // 推送渠道
  const [channels, setChannels] = useState<PushChannelRead[]>([])
  const [chName, setChName] = useState("")
  const [chType, setChType] = useState<PushChannelType>("feishu")
  const [chField1, setChField1] = useState("")
  const [chField2, setChField2] = useState("")
  const [chSaving, setChSaving] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)

  // 本地 Agent 健康 (openclaw / hermes 连通性)
  const [agentHealth, setAgentHealth] = useState<LocalAgentHealth | null>(null)

  // Embedding 模型 API
  const [emb, setEmb] = useState<EmbeddingConfig | null>(null)
  const [embBase, setEmbBase] = useState("")
  const [embKey, setEmbKey] = useState("")
  const [embModel, setEmbModel] = useState("")
  const [embSaving, setEmbSaving] = useState(false)
  const [embMsg, setEmbMsg] = useState<string | null>(null)

  // LLM 默认模型 (画布新建 LLM 节点默认用此模型)
  const [llmDefault, setLlmDefault] = useState("")
  const [llmDefaultSaving, setLlmDefaultSaving] = useState(false)
  const [llmDefaultMsg, setLlmDefaultMsg] = useState<string | null>(null)

  const loadAll = async () => {
    setLoading(true)
    // 各区块独立加载, 单个接口失败不影响其它区块展示 (Promise.allSettled)
    const [providersR, modelsR, toolsR, channelsR, embR, llmR, healthR] = await Promise.allSettled([
      providerApi.list(),
      providerApi.listModels(),
      localAgentApi.listTools(),
      pushChannelApi.list(),
      systemApi.getEmbedding(),
      systemApi.getLlmDefault(),
      localAgentApi.health(),
    ])
    if (providersR.status === "fulfilled") setProviders(providersR.value.data)
    if (modelsR.status === "fulfilled") setModels(modelsR.value.data)
    if (toolsR.status === "fulfilled") setTools(toolsR.value.data)
    if (channelsR.status === "fulfilled") setChannels(channelsR.value.data)
    if (embR.status === "fulfilled") {
      setEmb(embR.value.data)
      setEmbBase(embR.value.data.base_url)
      setEmbModel(embR.value.data.model)
    }
    if (llmR.status === "fulfilled") setLlmDefault(llmR.value.data.default_model || "")
    if (healthR.status === "fulfilled") setAgentHealth(healthR.value.data)
    setLoading(false)
  }

  useEffect(() => {
    loadAll()
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
        model: chatModel,
      })
      setChatResponse(resp.data)
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "请求失败，请检查供应商状态")
    } finally {
      setChatting(false)
    }
  }

  const handleSaveKey = async () => {
    setKeySaving(true)
    setKeyMsg(null)
    try {
      await userApi.updateMe({ openai_api_key: openaiKey })
      setOpenaiKey("")
      await fetchMe()
      setKeyMsg(openaiKey ? "OpenAI API Key 已保存" : "已清除 API Key")
    } catch (err) {
      setKeyMsg(err instanceof Error ? err.message : "保存失败")
    } finally {
      setKeySaving(false)
    }
  }

  const handleClearKey = async () => {
    setKeySaving(true)
    setKeyMsg(null)
    try {
      await userApi.updateMe({ openai_api_key: "" })
      await fetchMe()
      setKeyMsg("已清除 API Key")
    } catch (err) {
      setKeyMsg(err instanceof Error ? err.message : "清除失败")
    } finally {
      setKeySaving(false)
    }
  }

  const handleAddChannel = async () => {
    if (!chName.trim() || !chField1.trim()) return
    setChSaving(true)
    try {
      const config: Record<string, string> = {}
      if (chType === "feishu" || chType === "wechat") config.webhook_url = chField1
      else if (chType === "telegram") {
        config.bot_token = chField1
        config.chat_id = chField2
      } else if (chType === "hermes") config.channel = chField1
      await pushChannelApi.create({ name: chName.trim(), type: chType, config })
      setChName("")
      setChField1("")
      setChField2("")
      await loadAll()
    } catch {
      // 拦截器处理
    } finally {
      setChSaving(false)
    }
  }

  const handleDeleteChannel = async (id: string, name: string) => {
    if (!confirm(`确认删除推送渠道「${name}」？`)) return
    try {
      await pushChannelApi.delete(id)
      toast.success("渠道已删除")
      await loadAll()
    } catch {
      // 拦截器处理
    }
  }

  // 测试发送: 用已保存渠道发一条测试消息
  const handleTestChannel = async (c: PushChannelRead) => {
    setTestingId(c.id)
    try {
      const resp = await notifyApi.send({
        title: "测试推送",
        content: `来自 Claw 平台的渠道连通性测试 (${c.name})`,
        channels: [],
        channel_ids: [c.id],
      })
      const failed = resp.data.results.filter((r) => !r.success)
      if (failed.length === 0) {
        toast.success(`渠道「${c.name}」测试发送成功`)
      } else {
        toast.error(`渠道「${c.name}」发送失败: ${failed[0].error ?? "未知错误"}`)
      }
    } catch {
      // 拦截器处理
    } finally {
      setTestingId(null)
    }
  }

  const handleSaveEmb = async () => {
    setEmbSaving(true)
    setEmbMsg(null)
    try {
      const resp = await systemApi.setEmbedding({
        base_url: embBase,
        api_key: embKey,
        model: embModel,
      })
      setEmb(resp.data)
      setEmbKey("")
      setEmbMsg("已保存")
      await loadAll()
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } }).response?.status
      if (status === 403) setEmbMsg("保存失败：权限不足，需要管理员账号登录")
      else if (status === 401) setEmbMsg("保存失败：登录已过期，请重新登录")
      else setEmbMsg("保存失败：" + ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail || "请检查网络/后端"))
    } finally {
      setEmbSaving(false)
    }
  }

  const handleSaveLlmDefault = async () => {
    setLlmDefaultSaving(true)
    setLlmDefaultMsg(null)
    try {
      await systemApi.setLlmDefault(llmDefault)
      setLlmDefaultMsg("已保存")
    } catch {
      setLlmDefaultMsg("保存失败")
    } finally {
      setLlmDefaultSaving(false)
    }
  }

  const channelHint = CHANNEL_TYPES.find((c) => c.value === chType)?.hint ?? ""
  const isTelegram = chType === "telegram"

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">系统设置</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          模型供应商 · API Key · 推送渠道 · 本地工具 · 在线测试对话
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
                    本地 OpenClaw / Hermes 为一等公民 · 云端 OpenAI / Anthropic 兜底 · dev 环境含 Mock 兜底
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {providers.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">暂无已注册的模型供应商</p>
              ) : (
                providers.map((p) => {
                  const sMeta = statusMeta(p.status)
                  const dMeta = deployMeta(p.deploy)
                  return (
                    <div key={p.name} className="flex items-center justify-between rounded-lg border p-3">
                      <div className="flex items-center gap-3">
                        <span className={sMeta.dotClass} />
                        <div>
                          <div className="text-sm font-medium">{p.name}</div>
                          <div className="text-xs text-muted-foreground">{p.detail ?? sMeta.label}</div>
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

          {/* API Key 管理 */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <KeyRound className="h-5 w-5 text-muted-foreground" />
                <div>
                  <CardTitle className="text-base">API Key 管理</CardTitle>
                  <CardDescription>
                    OpenAI API Key 加密存储 (AES-256-GCM)，用于 LLM 兜底
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-sm">
                当前状态：
                <span className={user?.has_openai_key ? "text-green-600" : "text-muted-foreground"}>
                  {user?.has_openai_key ? "已配置 OpenAI Key" : "未配置"}
                </span>
              </div>
              <div className="flex gap-2">
                <Input
                  type="password"
                  value={openaiKey}
                  onChange={(e) => setOpenaiKey(e.target.value)}
                  placeholder="sk-..."
                  disabled={keySaving}
                />
                <Button onClick={handleSaveKey} disabled={keySaving || !openaiKey.trim()}>
                  {keySaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  保存
                </Button>
                {user?.has_openai_key && (
                  <Button variant="outline" onClick={handleClearKey} disabled={keySaving}>
                    清除
                  </Button>
                )}
              </div>
              {keyMsg && <div className="text-xs text-muted-foreground">{keyMsg}</div>}
            </CardContent>
          </Card>

          {/* 默认模型 (画布新建 LLM 节点默认使用) */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Cpu className="h-5 w-5 text-muted-foreground" />
                <div>
                  <CardTitle className="text-base">默认模型</CardTitle>
                  <CardDescription>
                    Agent 画布里新建 LLM 节点默认使用此模型；从已注册模型列表选择
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                value={llmDefault}
                onChange={(e) => setLlmDefault(e.target.value)}
              >
                <option value="default">default (自动: Kaiweb 优先)</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.provider})
                  </option>
                ))}
              </select>
              <Button onClick={handleSaveLlmDefault} disabled={llmDefaultSaving}>
                {llmDefaultSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                保存
              </Button>
              {llmDefaultMsg && (
                <p className={cn("text-xs", llmDefaultMsg === "已保存" ? "text-green-600" : "text-destructive")}>
                  {llmDefaultMsg}
                </p>
              )}
            </CardContent>
          </Card>

          {/* Embedding 模型 API */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Cpu className="h-5 w-5 text-muted-foreground" />
                <div>
                  <CardTitle className="text-base">Embedding 模型 API</CardTitle>
                  <CardDescription>
                    OpenAI 兼容 /v1/embeddings · 优先于此处的 TEI 与兜底向量 · 向量化走此接口
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-sm">
                当前来源：
                <span className={
                  emb?.source === "api" ? "text-green-600" :
                  emb?.source === "tei" ? "text-blue-600" : "text-amber-600"
                }>
                  {emb?.source === "api" ? "API（已配置）" : emb?.source === "tei" ? "TEI sidecar" : "哈希兜底（无真实向量）"}
                </span>
              </div>
              <div className="space-y-2">
                <Label htmlFor="emb-base">Base URL</Label>
                <Input
                  id="emb-base"
                  value={embBase}
                  onChange={(e) => setEmbBase(e.target.value)}
                  placeholder="https://api.example.com/v1"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="emb-model">模型名</Label>
                <Input
                  id="emb-model"
                  value={embModel}
                  onChange={(e) => setEmbModel(e.target.value)}
                  placeholder="bge-m3 / text-embedding-3-large 等 (需 1024 维)"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="emb-key">API Key {emb?.has_key ? "（已配置，留空保存则不清除）" : ""}</Label>
                <Input
                  id="emb-key"
                  type="password"
                  value={embKey}
                  onChange={(e) => setEmbKey(e.target.value)}
                  placeholder={emb?.has_key ? "已配置（如需更新请输入新 Key）" : "sk-..."}
                />
              </div>
              <Button onClick={handleSaveEmb} disabled={embSaving}>
                {embSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                保存
              </Button>
              {embMsg && (
                <p className={cn("text-xs", embMsg.startsWith("保存失败") ? "text-destructive" : "text-green-600")}>
                  {embMsg}
                </p>
              )}
            </CardContent>
          </Card>

          {/* 推送渠道配置 */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Send className="h-5 w-5 text-muted-foreground" />
                <div>
                  <CardTitle className="text-base">推送渠道配置</CardTitle>
                  <CardDescription>飞书 / 企微 / Telegram / Hermes · 敏感字段加密存储</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                {channels.length === 0 ? (
                  <p className="text-sm text-muted-foreground">暂无已配置渠道</p>
                ) : (
                  channels.map((c) => (
                    <div key={c.id} className="flex items-center justify-between rounded-lg border p-3 text-sm">
                      <div>
                        <span className="font-medium">{c.name}</span>
                        <span className="ml-2 rounded bg-secondary px-1.5 py-0.5 text-xs text-muted-foreground">
                          {c.type}
                        </span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          title="测试发送"
                          disabled={testingId === c.id}
                          onClick={() => handleTestChannel(c)}
                        >
                          {testingId === c.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Zap className="h-4 w-4" />
                          )}
                          测试
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => handleDeleteChannel(c.id, c.name)}>
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </div>
                  ))
                )}
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
                <Input placeholder="渠道名称" value={chName} onChange={(e) => setChName(e.target.value)} />
                <select
                  className="h-9 rounded-md border bg-background px-2 text-sm"
                  value={chType}
                  onChange={(e) => setChType(e.target.value as PushChannelType)}
                >
                  {CHANNEL_TYPES.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
                <Input
                  placeholder={isTelegram ? "bot_token" : channelHint}
                  value={chField1}
                  onChange={(e) => setChField1(e.target.value)}
                />
                {isTelegram ? (
                  <Input placeholder="chat_id" value={chField2} onChange={(e) => setChField2(e.target.value)} />
                ) : (
                  <Button onClick={handleAddChannel} disabled={chSaving || !chName.trim() || !chField1.trim()}>
                    {chSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                    添加
                  </Button>
                )}
              </div>
              {isTelegram && (
                <Button onClick={handleAddChannel} disabled={chSaving || !chName.trim() || !chField1.trim() || !chField2.trim()}>
                  {chSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                  添加 Telegram 渠道
                </Button>
              )}
            </CardContent>
          </Card>

          {/* 本地工具 */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Wrench className="h-5 w-5 text-muted-foreground" />
                <div>
                  <CardTitle className="text-base">本地工具 (Skills)</CardTitle>
                  <CardDescription>
                    扫描 deploy/openclaw/skills 与 deploy/hermes/skills · OpenClaw 在线工具自动合并
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {/* OpenClaw / Hermes 健康状态 */}
              <div className="flex flex-wrap items-center gap-4 rounded-lg border p-3 text-sm">
                <span className="text-muted-foreground">本地 Agent 健康:</span>
                <span className="flex items-center gap-1.5">
                  <span className={agentHealth?.openclaw ? "h-2 w-2 rounded-full bg-green-500" : "h-2 w-2 rounded-full bg-red-500"} />
                  OpenClaw
                  <span className="text-xs text-muted-foreground">{agentHealth?.openclaw ? "在线" : "离线"}</span>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className={agentHealth?.hermes ? "h-2 w-2 rounded-full bg-green-500" : "h-2 w-2 rounded-full bg-red-500"} />
                  Hermes
                  <span className="text-xs text-muted-foreground">{agentHealth?.hermes ? "在线" : "离线"}</span>
                </span>
              </div>
              {tools.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">未发现本地工具</p>
              ) : (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {tools.map((t) => (
                    <div key={t.id} className="rounded-lg border p-3 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{t.name}</span>
                        <span className="rounded bg-secondary px-1.5 py-0.5 text-xs text-muted-foreground">
                          {t.source}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">{t.description}</div>
                    </div>
                  ))}
                </div>
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
                    <div key={m.id} className="flex items-center justify-between rounded-lg border p-3 text-sm">
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
          <CardDescription>向默认模型供应商发送一条消息，验证连通性与响应 (dev 环境无 Key 时走 Mock 兜底)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="chat-input">消息内容</Label>
            <div className="flex gap-2">
              <select
                className="h-9 w-44 rounded-md border border-input bg-background px-2 text-sm"
                value={chatModel}
                onChange={(e) => setChatModel(e.target.value)}
                disabled={chatting}
              >
                <option value="default">default (自动)</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
              <Input
                id="chat-input"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="输入测试消息，例如：你好"
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                disabled={chatting}
              />
              <Button onClick={handleSend} disabled={chatting || !chatInput.trim()}>
                {chatting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
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
              <div className="whitespace-pre-wrap break-words text-sm">{chatResponse.content}</div>
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
