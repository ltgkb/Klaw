import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { AlertTriangle, Brain, Database, GitBranch, Type, Bell, BrainCog, Trash2, Plus, X, Play, Repeat2, Square, Globe, Loader2, RefreshCw, Settings2, Wrench } from "lucide-react"
import { kbApi, localAgentApi, providerApi, pushChannelApi, type KBRead, type NodeType, type ModelInfo, type PushChannelRead, type ToolInfo } from "@/lib/api"
import type { Node } from "@xyflow/react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import type { FlowNodeData, CanvasNodeType } from "@/components/flow/nodes"

const NODE_ICONS: Record<CanvasNodeType, typeof Brain> = {
  start: Play,
  end: Square,
  llm: Brain,
  retrieval: Database,
  condition: GitBranch,
  loop: Repeat2,
  text: Type,
  notify: Bell,
  memory: BrainCog,
  http: Globe,
  tool: Wrench,
}

const NODE_LABELS: Record<CanvasNodeType, string> = {
  start: "开始",
  end: "结束",
  llm: "LLM 对话",
  retrieval: "知识库检索",
  condition: "条件分支",
  loop: "循环",
  text: "文本拼接",
  notify: "消息推送",
  memory: "记忆读写",
  http: "HTTP 请求",
  tool: "本地工具",
}

/** 模型选择器: 从 /providers/models 拉取真实模型列表 */
function ModelSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [loaded, setLoaded] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    setLoaded(false)
    setLoadFailed(false)
    providerApi
      .listModels()
      .then((response) => {
        if (active) setModels(response.data)
      })
      .catch(() => {
        if (active) {
          setModels([])
          setLoadFailed(true)
        }
      })
      .finally(() => {
        if (active) setLoaded(true)
      })
    return () => {
      active = false
    }
  }, [reloadKey])

  // 后端可能已经返回 default；统一按 id 去重，当前自定义值仍保留显示。
  const options = Array.from(new Map(models.map((model) => [model.id, model])).values())
  if (!options.some((model) => model.id === "default")) {
    options.unshift({ id: "default", name: "default (自动路由)", provider: "auto" })
  }
  if (value && !options.some((m) => m.id === value)) {
    options.unshift({ id: value, name: value, provider: "自定义" })
  }

  return (
    <>
      <select
        id="llm-model"
        className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
        value={value || "default"}
        onChange={(e) => onChange(e.target.value)}
      >
        {!loaded ? (
          <option value="default">加载模型中…</option>
        ) : (
          options.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name} ({m.provider})
            </option>
          ))
        )}
      </select>
      {loadFailed ? (
        <div className="flex items-center justify-between text-xs text-destructive">
          <span>模型列表加载失败，当前仅保留自动路由</span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setReloadKey((key) => key + 1)}
            title="重新加载模型"
            aria-label="重新加载模型"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          default 按当前可用状态自动路由；Mock 仅用于开发环境兜底
        </p>
      )}
    </>
  )
}

/** 检索节点知识库选择器：UI 展示名称，保存时仍使用后端稳定 UUID。 */
function KnowledgeBaseSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [knowledgeBases, setKnowledgeBases] = useState<KBRead[]>([])
  const [loaded, setLoaded] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    setLoaded(false)
    setLoadFailed(false)
    kbApi
      .list(1, 100)
      .then((response) => {
        if (active) setKnowledgeBases(response.data.items)
      })
      .catch(() => {
        if (active) {
          setKnowledgeBases([])
          setLoadFailed(true)
        }
      })
      .finally(() => {
        if (active) setLoaded(true)
      })
    return () => {
      active = false
    }
  }, [reloadKey])

  const selectedStillExists = knowledgeBases.some((knowledgeBase) => knowledgeBase.id === value)

  return (
    <div className="space-y-2">
      <Label htmlFor="ret-kb">知识库</Label>
      <select
        id="ret-kb"
        className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={!loaded || loadFailed}
      >
        <option value="">{loaded ? "选择知识库" : "加载知识库中…"}</option>
        {value && !selectedStillExists && (
          <option value={value}>当前配置的知识库（已不可见，请重新选择）</option>
        )}
        {knowledgeBases.map((knowledgeBase) => (
          <option key={knowledgeBase.id} value={knowledgeBase.id}>
            {knowledgeBase.name}
          </option>
        ))}
      </select>
      {loadFailed ? (
        <div className="flex items-center justify-between text-xs text-destructive">
          <span>知识库列表加载失败</span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setReloadKey((key) => key + 1)}
            title="重新加载知识库"
            aria-label="重新加载知识库"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      ) : knowledgeBases.length === 0 && loaded ? (
        <p className="text-xs text-muted-foreground">
          暂无知识库，<Link to="/kb" className="underline">先创建知识库</Link>
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">选择名称后，工作流会保存对应知识库引用。</p>
      )}
    </div>
  )
}

function ToolSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let active = true
    localAgentApi
      .listTools()
      .then((response) => {
        if (active) setTools(response.data)
      })
      .catch(() => {
        if (active) setTools([])
      })
      .finally(() => {
        if (active) setLoaded(true)
      })
    return () => {
      active = false
    }
  }, [])

  const executableTools = tools.filter((tool) => tool.executable)
  const selected = executableTools.find((tool) => tool.id === value)
  return (
    <>
      <select
        id="tool-id"
        className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{loaded ? "选择工具" : "加载工具中…"}</option>
        {executableTools.map((tool) => (
          <option key={tool.id} value={tool.id}>{tool.name} ({tool.source})</option>
        ))}
      </select>
      {selected?.description && (
        <p className="text-xs text-muted-foreground">{selected.description}</p>
      )}
    </>
  )
}

const CHANNEL_TYPE_LABELS: Record<PushChannelRead["type"], string> = {
  feishu: "飞书",
  wechat: "企业微信",
  telegram: "Telegram",
  hermes: "Hermes",
}

function NotifyChannelSelector({
  value,
  legacyCount,
  onChange,
  onClearLegacy,
}: {
  value: string[]
  legacyCount: number
  onChange: (ids: string[]) => void
  onClearLegacy: () => void
}) {
  const [channels, setChannels] = useState<PushChannelRead[]>([])
  const [loading, setLoading] = useState(true)
  const [loadFailed, setLoadFailed] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadFailed(false)
    pushChannelApi
      .list()
      .then((response) => {
        if (active) setChannels(response.data)
      })
      .catch(() => {
        if (active) setLoadFailed(true)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [reloadKey])

  const toggle = (channelId: string) => {
    onChange(
      value.includes(channelId)
        ? value.filter((id) => id !== channelId)
        : [...value, channelId],
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label>已保存渠道</Label>
        <Button asChild variant="ghost" size="sm" className="h-7 px-2 text-xs">
          <Link to="/settings">
            <Settings2 className="h-3.5 w-3.5" />
            管理渠道
          </Link>
        </Button>
      </div>

      {legacyCount > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <div className="min-w-0 flex-1">
            <p>此旧节点含 {legacyCount} 个内联渠道配置。</p>
            <button type="button" className="mt-1 font-medium underline" onClick={onClearLegacy}>
              清除旧配置
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex h-16 items-center justify-center rounded-md border">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        </div>
      ) : loadFailed ? (
        <div className="flex h-16 items-center justify-between rounded-md border px-3 text-sm text-destructive">
          <span>渠道加载失败</span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0"
            title="重新加载渠道"
            onClick={() => setReloadKey((key) => key + 1)}
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      ) : channels.length === 0 ? (
        <p className="rounded-md border p-3 text-sm text-muted-foreground">暂无已保存渠道</p>
      ) : (
        <div className="max-h-52 space-y-1 overflow-auto rounded-md border p-1">
          {channels.map((channel) => (
            <label
              key={channel.id}
              className="flex min-h-10 cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-accent"
            >
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-input"
                checked={value.includes(channel.id)}
                onChange={() => toggle(channel.id)}
              />
              <span className="min-w-0 flex-1 truncate text-sm">{channel.name}</span>
              <span className="text-xs text-muted-foreground">{CHANNEL_TYPE_LABELS[channel.type]}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

interface Props {
  node: Node | null
  allNodes?: Node[]
  onChange: (id: string, data: Partial<Node["data"]>) => void
  onDelete: (id: string) => void
}

/** 变量选项 */
interface VarOpt {
  token: string
  label: string
}

/** 变量选择器: 按钮弹下拉, 列出可引用变量, 选中后插入到模板。
 *  下拉用 fixed 定位, 避免被配置面板的 overflow-auto 裁切。 */
function VarPicker({ vars, onInsert }: { vars: VarOpt[]; onInsert: (token: string) => void }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const btnRef = useRef<HTMLButtonElement | null>(null)
  if (vars.length === 0) return null

  const toggle = () => {
    if (!open && btnRef.current) {
      const r = btnRef.current.getBoundingClientRect()
      // 下拉向左展开 (宽 208px), 避免超出右边界
      setPos({ x: Math.max(8, r.right - 208), y: r.bottom + 4 })
    }
    setOpen((o) => !o)
  }

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className="inline-flex h-8 items-center gap-1 rounded-md border border-input bg-background px-2 text-xs hover:bg-accent"
        onClick={toggle}
      >
        <Plus className="h-3 w-3" />
        插入变量
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="fixed z-50 max-h-60 w-52 overflow-auto rounded-md border bg-background p-1 shadow-lg"
            style={{ top: pos.y, left: pos.x }}
          >
            {vars.map((v) => (
              <button
                key={v.token}
                type="button"
                className="block w-full rounded px-2 py-1 text-left text-xs hover:bg-accent"
                onClick={() => {
                  onInsert(v.token)
                  setOpen(false)
                }}
              >
                {v.label}
              </button>
            ))}
          </div>
        </>
      )}
    </>
  )
}

export function NodeConfigPanel({ node, allNodes = [], onChange, onDelete }: Props) {
  if (!node) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-6 text-center">
        <p className="text-sm text-muted-foreground">
          选中一个节点以编辑配置
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          从左侧元素栏添加新节点
        </p>
      </div>
    )
  }

  const nodeType = node.type as CanvasNodeType
  const Icon = NODE_ICONS[nodeType] ?? Type
  const nodeData = node.data as unknown as FlowNodeData
  const config = nodeData.config || {}

  const updateConfig = (key: string, value: unknown) => {
    onChange(node.id, {
      ...nodeData,
      config: { ...config, [key]: value },
    })
  }

  // 在某个模板字段末尾追加变量 token
  const insertVar = (key: string, token: string) => {
    const cur = (config[key as keyof typeof config] as string) || ""
    updateConfig(key, cur + token)
  }

  // 可引用变量: 系统变量 + 各节点输出(按 label) + 开始节点命名输入
  const availableVars: VarOpt[] = [
    { token: "{input}", label: "{input} 执行输入" },
    { token: "{sys.query}", label: "{sys.query} 用户消息" },
    { token: "{history}", label: "{history} 对话历史" },
    ...allNodes
      .filter((n) => n.id !== node.id)
      .map((n) => ({
        token: `{${(n.data as { label?: string }).label || n.id}}`,
        label: `{${(n.data as { label?: string }).label || n.id}} 节点输出`,
      })),
    ...allNodes
      .filter((n) => n.type === "start")
      .flatMap((n) => {
        const inputs = (n.data as { config?: { inputs?: { name?: string }[] } }).config?.inputs || []
        return inputs
          .filter((i) => i.name)
          .map((i) => ({ token: `{${i.name}}`, label: `{${i.name}} 开始输入` }))
      }),
    ...allNodes
      .filter((n) => {
        if (n.type !== "loop") return false
        const loopConfig = (n.data as { config?: Record<string, unknown> }).config || {}
        return loopConfig.body_node_id === node.id
      })
      .flatMap((n) => {
        const loopConfig = (n.data as { config?: Record<string, unknown> }).config || {}
        const itemVar = (loopConfig.item_variable as string) || "item"
        const indexVar = (loopConfig.index_variable as string) || "index"
        return [
          { token: `{${itemVar}}`, label: `{${itemVar}} 当前循环项` },
          { token: `{${indexVar}}`, label: `{${indexVar}} 当前索引` },
        ]
      }),
  ]

  const loopBodyOptions = allNodes.filter(
    (n) => n.id !== node.id && ["llm", "retrieval", "text", "notify", "memory", "tool"].includes(n.type || ""),
  )

  const updateLabel = (label: string) => {
    onChange(node.id, { ...nodeData, label })
  }

  return (
    <div className="flex h-full flex-col">
      {/* 头部 */}
      <div className="flex items-center gap-2 border-b p-3">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-semibold">{NODE_LABELS[nodeType]}</span>
        <code className="ml-auto text-xs text-muted-foreground">{node.id.slice(0, 8)}</code>
      </div>

      {/* 配置表单 */}
      <div className="flex-1 space-y-4 overflow-auto p-4">
        {/* 通用: 节点名称 */}
        <div className="space-y-2">
          <Label htmlFor="node-label">节点名称</Label>
          <Input
            id="node-label"
            value={nodeData.label}
            onChange={(e) => updateLabel(e.target.value)}
            placeholder="节点显示名"
          />
        </div>

        {/* 节点类型特定配置 */}
        {nodeType === "start" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>输入变量</Label>
              <Button
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={() => {
                  const inputs = [...((config.inputs as { name: string; value: string; type?: string }[]) || []), { name: "", value: "", type: "string" }]
                  updateConfig("inputs", inputs)
                }}
              >
                <Plus className="h-3 w-3" /> 添加输入
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              定义工作流输入变量。下游可用 {`{变量名}`} 引用；留空则用执行时的 {`{input}`}。
            </p>
            <div className="space-y-2">
              {(((config.inputs as { name: string; value: string }[]) || []).length === 0) && (
                <p className="rounded-md border bg-muted/30 p-2 text-xs text-muted-foreground">
                  未定义输入变量，将使用执行输入 {`{input}`}。
                </p>
              )}
              {((config.inputs as { name: string; value: string; type?: string }[]) || []).map((inp, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input
                    className="h-8 w-28 text-xs"
                    placeholder="变量名(如 query)"
                    value={inp.name}
                    onChange={(e) => {
                      const inputs = [...((config.inputs as { name: string; value: string; type?: string }[]) || [])]
                      inputs[i] = { ...inp, name: e.target.value }
                      updateConfig("inputs", inputs)
                    }}
                  />
                  <select
                    className="h-8 w-24 rounded-md border border-input bg-background px-1 text-xs"
                    value={inp.type || "string"}
                    onChange={(e) => {
                      const inputs = [...((config.inputs as { name: string; value: string; type?: string }[]) || [])]
                      inputs[i] = { ...inp, type: e.target.value }
                      updateConfig("inputs", inputs)
                    }}
                  >
                    <option value="string">字符串</option>
                    <option value="text">长文本</option>
                    <option value="integer">整数</option>
                    <option value="float">小数</option>
                    <option value="bool">布尔</option>
                  </select>
                  <Input
                    className="h-8 flex-1 text-xs"
                    placeholder="默认值(可空, 对话时由用户消息填充)"
                    value={inp.value}
                    onChange={(e) => {
                      const inputs = [...((config.inputs as { name: string; value: string; type?: string }[]) || [])]
                      inputs[i] = { ...inp, value: e.target.value }
                      updateConfig("inputs", inputs)
                    }}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 px-2"
                    onClick={() => {
                      const inputs = [...((config.inputs as { name: string; value: string; type?: string }[]) || [])]
                      inputs.splice(i, 1)
                      updateConfig("inputs", inputs)
                    }}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}
        {nodeType === "end" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="end-output">输出变量</Label>
              <VarPicker vars={availableVars} onInsert={(t) => updateConfig("output", t.replace(/^\{|\}$/g, ""))} />
            </div>
            <Input
              id="end-output"
              value={(config.output as string) || ""}
              onChange={(e) => updateConfig("output", e.target.value)}
              placeholder="选择要输出的变量, 如 LLM / input / query; 留空取最后节点输出"
            />
            <p className="text-xs text-muted-foreground">
              工作流最终结果 = 此变量的值。点右上角插入变量; 对话 Agent 的回答即取自此。
            </p>
          </div>
        )}
        {nodeType === "llm" && (
          <>
            <div className="space-y-2">
              <Label htmlFor="llm-model">模型</Label>
              <ModelSelect
                value={(config.model as string) || "default"}
                onChange={(v) => updateConfig("model", v)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="llm-system">系统提示词</Label>
              <textarea
                id="llm-system"
                className={cn(
                  "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2",
                  "text-sm ring-offset-background placeholder:text-muted-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
                value={(config.system_prompt as string) || ""}
                onChange={(e) => updateConfig("system_prompt", e.target.value)}
                placeholder="你是一个有用的助手..."
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="llm-user">用户消息模板</Label>
                <VarPicker vars={availableVars} onInsert={(t) => insertVar("user_template", t)} />
              </div>
              <textarea
                id="llm-user"
                className={cn(
                  "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2",
                  "text-sm ring-offset-background placeholder:text-muted-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
                value={(config.user_template as string) || ""}
                onChange={(e) => updateConfig("user_template", e.target.value)}
                placeholder="用 {节点名} 引用上游输出, {input} 引用输入; 可点右上角插入变量"
              />
              <p className="text-xs text-muted-foreground">
                {`{节点名} 引用上游节点输出, {input}/{sys.query} 引用输入, {history} 引用对话历史`}
              </p>
            </div>
          </>
        )}

        {nodeType === "retrieval" && (
          <>
            <KnowledgeBaseSelect
              value={(config.kb_id as string) || ""}
              onChange={(value) => updateConfig("kb_id", value)}
            />
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="ret-query">查询模板</Label>
                <VarPicker vars={availableVars} onInsert={(t) => insertVar("query_template", t)} />
              </div>
              <Input
                id="ret-query"
                value={(config.query_template as string) || ""}
                onChange={(e) => updateConfig("query_template", e.target.value)}
                placeholder="{input}"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ret-topk">Top-K</Label>
              <Input
                id="ret-topk"
                type="number"
                value={(config.top_k as number) ?? 5}
                onChange={(e) => updateConfig("top_k", parseInt(e.target.value) || 5)}
                min={1}
                max={50}
              />
            </div>
          </>
        )}

        {nodeType === "condition" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label>分支条件</Label>
              <Button
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={() => {
                  const cases = [
                    ...((config.cases as { id: string; name: string; expression: string }[]) || []),
                    { id: `case${Date.now()}`, name: `条件${(((config.cases as unknown[]) || []).length) + 1}`, expression: "" },
                  ]
                  updateConfig("cases", cases)
                }}
              >
                <Plus className="h-3 w-3" /> 添加条件
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              按顺序匹配，首个为真的分支被执行。从节点右侧对应分支连线到下游；都不满足走「默认」分支。
              支持 == != &gt; &gt;= &lt; &lt;= contains。
            </p>
            <div className="space-y-2">
              {(((config.cases as { id: string; name: string; expression: string }[]) || []).length === 0) && (
                <p className="rounded-md border bg-muted/30 p-2 text-xs text-muted-foreground">
                  未添加条件，将直接走默认分支。
                </p>
              )}
              {((config.cases as { id: string; name: string; expression: string }[]) || []).map((c, i) => (
                <div key={c.id || i} className="space-y-1.5 rounded-md border p-2">
                  <div className="flex items-center gap-2">
                    <Input
                      className="h-8 flex-1 text-xs"
                      placeholder="分支名 (如 高分)"
                      value={c.name}
                      onChange={(e) => {
                        const cases = [...((config.cases as { id: string; name: string; expression: string }[]) || [])]
                        cases[i] = { ...c, name: e.target.value }
                        updateConfig("cases", cases)
                      }}
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 px-2"
                      onClick={() => {
                        const cases = [...((config.cases as { id: string; name: string; expression: string }[]) || [])]
                        cases.splice(i, 1)
                        updateConfig("cases", cases)
                      }}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                  <div className="flex items-center gap-2">
                    <VarPicker vars={availableVars} onInsert={(t) => {
                      const cases = [...((config.cases as { id: string; name: string; expression: string }[]) || [])]
                      cases[i] = { ...c, expression: (c.expression || "") + t }
                      updateConfig("cases", cases)
                    }} />
                    <Input
                      className="h-8 flex-1 text-xs"
                      placeholder="{score} > 80"
                      value={c.expression}
                      onChange={(e) => {
                        const cases = [...((config.cases as { id: string; name: string; expression: string }[]) || [])]
                        cases[i] = { ...c, expression: e.target.value }
                        updateConfig("cases", cases)
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="space-y-2">
              <Label>默认分支名 (都不满足时)</Label>
              <Input
                className="h-8 text-xs"
                value={(config.default_name as string) || ""}
                onChange={(e) => updateConfig("default_name", e.target.value)}
                placeholder="默认"
              />
            </div>
          </div>
        )}

        {nodeType === "loop" && (
          <>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="loop-items">循环输入</Label>
                <VarPicker vars={availableVars} onInsert={(t) => insertVar("items_template", t)} />
              </div>
              <textarea
                id="loop-items"
                className={cn(
                  "flex min-h-[72px] w-full rounded-md border border-input bg-background px-3 py-2",
                  "text-sm ring-offset-background placeholder:text-muted-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
                value={(config.items_template as string) || ""}
                onChange={(e) => updateConfig("items_template", e.target.value)}
                placeholder={'{items} 或 ["北京", "上海"]'}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="loop-body">循环体节点（需未连线）</Label>
              <select
                id="loop-body"
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                value={(config.body_node_id as string) || ""}
                onChange={(e) => updateConfig("body_node_id", e.target.value)}
              >
                <option value="">选择节点</option>
                {loopBodyOptions.map((n) => {
                  const type = n.type as NodeType
                  const label = (n.data as { label?: string }).label || n.id
                  return <option key={n.id} value={n.id}>{label} · {NODE_LABELS[type]}</option>
                })}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-2">
                <Label htmlFor="loop-item-var">循环项变量</Label>
                <Input
                  id="loop-item-var"
                  value={(config.item_variable as string) || "item"}
                  onChange={(e) => updateConfig("item_variable", e.target.value)}
                  placeholder="item"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="loop-index-var">索引变量</Label>
                <Input
                  id="loop-index-var"
                  value={(config.index_variable as string) || "index"}
                  onChange={(e) => updateConfig("index_variable", e.target.value)}
                  placeholder="index"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="loop-max">最大次数</Label>
              <Input
                id="loop-max"
                type="number"
                min={1}
                max={100}
                value={(config.max_iterations as number) ?? 20}
                onChange={(e) => updateConfig("max_iterations", Number(e.target.value))}
              />
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-input"
                checked={Boolean(config.continue_on_error)}
                onChange={(e) => updateConfig("continue_on_error", e.target.checked)}
              />
              单次失败后继续
            </label>
          </>
        )}

        {nodeType === "text" && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="text-tmpl">文本模板</Label>
              <VarPicker vars={availableVars} onInsert={(t) => insertVar("template", t)} />
            </div>
            <textarea
              id="text-tmpl"
              className={cn(
                "flex min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2",
                "text-sm ring-offset-background placeholder:text-muted-foreground",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              )}
              value={(config.template as string) || ""}
              onChange={(e) => updateConfig("template", e.target.value)}
              placeholder="拼接文本: {input} + {节点名}"
            />
            <p className="text-xs text-muted-foreground">
              {"{node_id} 引用上游节点输出, {input} 引用执行输入"}
            </p>
          </div>
        )}

        {nodeType === "notify" && (
          <>
            <div className="space-y-2">
              <Label htmlFor="notify-title">标题模板</Label>
              <Input
                id="notify-title"
                value={(config.title_template as string) || ""}
                onChange={(e) => updateConfig("title_template", e.target.value)}
                placeholder="Agent 执行结果"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="notify-content">内容模板</Label>
              <textarea
                id="notify-content"
                className={cn(
                  "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2",
                  "text-sm ring-offset-background placeholder:text-muted-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
                value={(config.content_template as string) || ""}
                onChange={(e) => updateConfig("content_template", e.target.value)}
                placeholder="结果: {node-1.output}"
              />
              <p className="text-xs text-muted-foreground">
                {"{node_id} 引用上游节点输出"}
              </p>
            </div>
            <NotifyChannelSelector
              value={(config.channel_ids as string[]) || []}
              legacyCount={((config.channels as unknown[]) || []).length}
              onChange={(channelIds) => {
                onChange(node.id, {
                  ...nodeData,
                  config: { ...config, channel_ids: channelIds, channels: [] },
                })
              }}
              onClearLegacy={() => updateConfig("channels", [])}
            />
          </>
        )}

        {nodeType === "memory" && (
          <>
            <div className="space-y-2">
              <Label htmlFor="mem-action">操作</Label>
              <select
                id="mem-action"
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                value={(config.action as string) || "save"}
                onChange={(e) => updateConfig("action", e.target.value)}
              >
                <option value="save">写入 (save)</option>
                <option value="load">读取 (load)</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="mem-key">记忆 Key</Label>
              <Input
                id="mem-key"
                value={(config.key as string) || ""}
                onChange={(e) => updateConfig("key", e.target.value)}
                placeholder="如: user_preference"
              />
            </div>
            {(config.action as string) !== "load" && (
              <div className="space-y-2">
                <Label htmlFor="mem-value">值模板 (save 时)</Label>
                <textarea
                  id="mem-value"
                  className={cn(
                    "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2",
                    "text-sm ring-offset-background placeholder:text-muted-foreground",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  )}
                  value={(config.value_template as string) || ""}
                  onChange={(e) => updateConfig("value_template", e.target.value)}
                  placeholder="{node-1.output}"
                />
                <p className="text-xs text-muted-foreground">
                  {"{node_id} 引用上游节点输出"}
                </p>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="mem-session">Session ID (可选)</Label>
              <Input
                id="mem-session"
                value={(config.session_id as string) || ""}
                onChange={(e) => updateConfig("session_id", e.target.value)}
                placeholder="留空 = 全局记忆"
              />
            </div>
          </>
        )}

        {nodeType === "http" && (
          <>
            <div className="space-y-2">
              <Label htmlFor="http-method">请求方法</Label>
              <select
                id="http-method"
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                value={(config.method as string) || "GET"}
                onChange={(e) => updateConfig("method", e.target.value)}
              >
                <option value="GET">GET</option>
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
                <option value="PATCH">PATCH</option>
                <option value="DELETE">DELETE</option>
              </select>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="http-url">URL</Label>
                <VarPicker vars={availableVars} onInsert={(t) => insertVar("url", t)} />
              </div>
              <Input
                id="http-url"
                value={(config.url as string) || ""}
                onChange={(e) => updateConfig("url", e.target.value)}
                placeholder="https://api.example.com/path 支持 {input}"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>请求头 (Headers)</Label>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 px-2 text-xs"
                  onClick={() => {
                    const headers = { ...((config.headers as Record<string, string>) || {}) }
                    if (!("" in headers)) headers[""] = ""
                    updateConfig("headers", headers)
                  }}
                >
                  <Plus className="h-3 w-3" /> 添加请求头
                </Button>
              </div>
              {Object.entries((config.headers as Record<string, string>) || {}).map(([k, v], i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input
                    className="h-8 w-28 text-xs"
                    placeholder="Header 名"
                    value={k}
                    onChange={(e) => {
                      const entries = Object.entries((config.headers as Record<string, string>) || {})
                      entries[i] = [e.target.value, v]
                      updateConfig("headers", Object.fromEntries(entries))
                    }}
                  />
                  <Input
                    className="h-8 flex-1 text-xs"
                    placeholder="值 (支持 {input})"
                    value={v}
                    onChange={(e) => {
                      const entries = Object.entries((config.headers as Record<string, string>) || {})
                      entries[i] = [k, e.target.value]
                      updateConfig("headers", Object.fromEntries(entries))
                    }}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 px-2"
                    onClick={() => {
                      const entries = Object.entries((config.headers as Record<string, string>) || {})
                      entries.splice(i, 1)
                      updateConfig("headers", Object.fromEntries(entries))
                    }}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                </div>
              ))}
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="http-body">请求体 (Body)</Label>
                <VarPicker vars={availableVars} onInsert={(t) => insertVar("body", t)} />
              </div>
              <textarea
                id="http-body"
                className={cn(
                  "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2",
                  "text-sm ring-offset-background placeholder:text-muted-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
                value={(config.body as string) || ""}
                onChange={(e) => updateConfig("body", e.target.value)}
                placeholder='JSON 或文本, 支持 {input} 等变量; GET 时留空'
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="http-timeout">超时 (秒)</Label>
              <Input
                id="http-timeout"
                type="number"
                value={(config.timeout_s as number) ?? 30}
                onChange={(e) => updateConfig("timeout_s", parseInt(e.target.value) || 30)}
                min={1}
                max={300}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              响应文本作为节点输出存入上下文, 下游可用 {`{节点名}`} 引用
            </p>
          </>
        )}

        {nodeType === "tool" && (
          <>
            <div className="space-y-2">
              <Label htmlFor="tool-id">工具</Label>
              <ToolSelect
                value={(config.tool_id as string) || ""}
                onChange={(toolId) => updateConfig("tool_id", toolId)}
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="tool-parameters">JSON 参数</Label>
                <VarPicker vars={availableVars} onInsert={(token) => insertVar("parameters_template", token)} />
              </div>
              <textarea
                id="tool-parameters"
                className={cn(
                  "flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2",
                  "font-mono text-xs ring-offset-background placeholder:text-muted-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
                value={(config.parameters_template as string) || "{}"}
                onChange={(event) => updateConfig("parameters_template", event.target.value)}
                placeholder={'{"url": "{input}"}'}
              />
            </div>
          </>
        )}
      </div>

      {/* 删除按钮 */}
      <div className="border-t p-3">
        <Button
          variant="outline"
          size="sm"
          className="w-full text-destructive hover:bg-destructive/5"
          onClick={() => onDelete(node.id)}
        >
          <Trash2 className="h-4 w-4" />
          删除节点
        </Button>
      </div>
    </div>
  )
}
