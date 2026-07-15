import { Brain, Database, GitBranch, Type, Bell, BrainCog, Trash2, Plus, X } from "lucide-react"
import type { NodeType } from "@/lib/api"
import type { Node } from "@xyflow/react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import type { FlowNodeData } from "@/components/flow/nodes"

const NODE_ICONS: Record<NodeType, typeof Brain> = {
  llm: Brain,
  retrieval: Database,
  condition: GitBranch,
  text: Type,
  notify: Bell,
  memory: BrainCog,
}

const NODE_LABELS: Record<NodeType, string> = {
  llm: "LLM 对话",
  retrieval: "知识库检索",
  condition: "条件分支",
  text: "文本拼接",
  notify: "消息推送",
  memory: "记忆读写",
}

interface Props {
  node: Node | null
  onChange: (id: string, data: Partial<Node["data"]>) => void
  onDelete: (id: string) => void
}

export function NodeConfigPanel({ node, onChange, onDelete }: Props) {
  if (!node) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-6 text-center">
        <p className="text-sm text-muted-foreground">
          选中一个节点以编辑配置
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          左侧拖拽节点到画布添加新节点
        </p>
      </div>
    )
  }

  const nodeType = node.type as NodeType
  const Icon = NODE_ICONS[nodeType] ?? Type
  const nodeData = node.data as unknown as FlowNodeData
  const config = nodeData.config || {}

  const updateConfig = (key: string, value: unknown) => {
    onChange(node.id, {
      ...nodeData,
      config: { ...config, [key]: value },
    })
  }

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
        {nodeType === "llm" && (
          <>
            <div className="space-y-2">
              <Label htmlFor="llm-model">模型</Label>
              <Input
                id="llm-model"
                value={(config.model as string) || ""}
                onChange={(e) => updateConfig("model", e.target.value)}
                placeholder="default (OpenClaw 优先)"
              />
              <p className="text-xs text-muted-foreground">
                default → OpenClaw → OpenAI → Anthropic fallback
              </p>
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
              <Label htmlFor="llm-user">用户消息模板</Label>
              <textarea
                id="llm-user"
                className={cn(
                  "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2",
                  "text-sm ring-offset-background placeholder:text-muted-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
                value={(config.user_template as string) || ""}
                onChange={(e) => updateConfig("user_template", e.target.value)}
                placeholder="问题: {input} / 上游: {node-1}"
              />
              <p className="text-xs text-muted-foreground">
                {"{node_id} 引用上游节点输出, {input} 引用执行输入"}
              </p>
            </div>
          </>
        )}

        {nodeType === "retrieval" && (
          <>
            <div className="space-y-2">
              <Label htmlFor="ret-kb">知识库 ID</Label>
              <Input
                id="ret-kb"
                value={(config.kb_id as string) || ""}
                onChange={(e) => updateConfig("kb_id", e.target.value)}
                placeholder="粘贴知识库 UUID"
              />
              <p className="text-xs text-muted-foreground">
                在知识库详情页可获取 UUID
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ret-query">查询模板</Label>
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
          <div className="space-y-2">
            <Label htmlFor="cond-expr">条件表达式</Label>
            <Input
              id="cond-expr"
              value={(config.expression as string) || ""}
              onChange={(e) => updateConfig("expression", e.target.value)}
              placeholder="{input} == '是'"
            />
            <p className="text-xs text-muted-foreground">
              支持 == / != / contains, 变量用 {"{node_id}"} 引用
            </p>
          </div>
        )}

        {nodeType === "text" && (
          <div className="space-y-2">
            <Label htmlFor="text-tmpl">文本模板</Label>
            <textarea
              id="text-tmpl"
              className={cn(
                "flex min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2",
                "text-sm ring-offset-background placeholder:text-muted-foreground",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              )}
              value={(config.template as string) || ""}
              onChange={(e) => updateConfig("template", e.target.value)}
              placeholder="拼接文本: {input} + {node-1}"
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
            <div className="space-y-2">
              <Label>推送渠道</Label>
              {((config.channels as Array<Record<string, string>>) || []).map((ch, i) => (
                <div key={i} className="space-y-1.5 rounded-md border p-2">
                  <div className="flex items-center gap-2">
                    <select
                      className="flex h-8 flex-1 rounded-md border border-input bg-background px-2 text-xs"
                      value={ch.type || "feishu"}
                      onChange={(e) => {
                        const channels = [...((config.channels as Array<Record<string, string>>) || [])]
                        channels[i] = { ...ch, type: e.target.value }
                        updateConfig("channels", channels)
                      }}
                    >
                      <option value="feishu">飞书</option>
                      <option value="wechat">企业微信</option>
                      <option value="telegram">Telegram</option>
                    </select>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 px-2"
                      onClick={() => {
                        const channels = [...((config.channels as Array<Record<string, string>>) || [])]
                        channels.splice(i, 1)
                        updateConfig("channels", channels)
                      }}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                  {ch.type === "telegram" ? (
                    <>
                      <Input
                        className="h-8 text-xs"
                        value={ch.bot_token || ""}
                        onChange={(e) => {
                          const channels = [...((config.channels as Array<Record<string, string>>) || [])]
                          channels[i] = { ...ch, bot_token: e.target.value }
                          updateConfig("channels", channels)
                        }}
                        placeholder="Bot Token"
                      />
                      <Input
                        className="h-8 text-xs"
                        value={ch.chat_id || ""}
                        onChange={(e) => {
                          const channels = [...((config.channels as Array<Record<string, string>>) || [])]
                          channels[i] = { ...ch, chat_id: e.target.value }
                          updateConfig("channels", channels)
                        }}
                        placeholder="Chat ID"
                      />
                    </>
                  ) : (
                    <Input
                      className="h-8 text-xs"
                      value={ch.webhook_url || ""}
                      onChange={(e) => {
                        const channels = [...((config.channels as Array<Record<string, string>>) || [])]
                        channels[i] = { ...ch, webhook_url: e.target.value }
                        updateConfig("channels", channels)
                      }}
                      placeholder="Webhook URL"
                    />
                  )}
                </div>
              ))}
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={() => {
                  const channels = [...((config.channels as Array<Record<string, string>>) || []), { type: "feishu", webhook_url: "" }]
                  updateConfig("channels", channels)
                }}
              >
                <Plus className="h-3 w-3" />
                添加渠道
              </Button>
            </div>
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
