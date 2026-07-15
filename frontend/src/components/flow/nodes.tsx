import { memo } from "react"
import { Handle, Position, type NodeProps } from "@xyflow/react"
import { Brain, Database, GitBranch, Type, Bell, BrainCog } from "lucide-react"
import { cn } from "@/lib/utils"
import type { NodeType, NodeState } from "@/lib/api"

/** 节点类型 → 图标 + 颜色 */
const NODE_META: Record<NodeType, { icon: typeof Brain; color: string; label: string }> = {
  llm: { icon: Brain, color: "border-blue-400 bg-blue-50", label: "LLM 对话" },
  retrieval: { icon: Database, color: "border-purple-400 bg-purple-50", label: "知识库检索" },
  condition: { icon: GitBranch, color: "border-amber-400 bg-amber-50", label: "条件分支" },
  text: { icon: Type, color: "border-gray-400 bg-gray-50", label: "文本拼接" },
  notify: { icon: Bell, color: "border-pink-400 bg-pink-50", label: "消息推送" },
  memory: { icon: BrainCog, color: "border-teal-400 bg-teal-50", label: "记忆读写" },
}

/** 执行状态 → 边框颜色 */
const STATE_BORDER: Record<string, string> = {
  running: "ring-2 ring-blue-500",
  success: "ring-2 ring-green-500",
  failed: "ring-2 ring-red-500",
}

export interface FlowNodeData {
  label: string
  config: Record<string, unknown>
  nodeState?: NodeState
}

function BaseNode({ id, type, data, selected }: NodeProps) {
  const nodeData = data as unknown as FlowNodeData
  const meta = NODE_META[(type as NodeType) ?? "text"] ?? NODE_META.text
  const Icon = meta.icon
  const nodeState = nodeData.nodeState
  const stateClass = nodeState?.status ? STATE_BORDER[nodeState.status] ?? "" : ""

  return (
    <div
      className={cn(
        "min-w-[180px] max-w-[240px] rounded-lg border-2 px-3 py-2 shadow-sm transition-shadow",
        meta.color,
        stateClass,
        selected && "ring-2 ring-primary",
      )}
    >
      {/* 输入 Handle (除入口节点外都有) */}
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !border-2 !border-gray-400 !bg-white"
      />

      {/* 节点头部 */}
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 shrink-0 text-gray-600" />
        <span className="text-xs font-medium text-gray-500">{meta.label}</span>
        {nodeState?.status === "running" && (
          <span className="ml-auto h-2 w-2 animate-pulse rounded-full bg-blue-500" />
        )}
        {nodeState?.status === "success" && (
          <span className="ml-auto h-2 w-2 rounded-full bg-green-500" />
        )}
        {nodeState?.status === "failed" && (
          <span className="ml-auto h-2 w-2 rounded-full bg-red-500" />
        )}
      </div>

      {/* 节点名称 */}
      <p className="mt-1 text-sm font-semibold text-gray-800 truncate" title={nodeData.label}>
        {nodeData.label || id}
      </p>

      {/* 配置摘要 */}
      <NodeSummary type={type as NodeType} config={nodeData.config} />

      {/* 执行输出预览 */}
      {nodeState?.output && (
        <p className="mt-1 text-xs text-gray-500 truncate" title={nodeState.output}>
          → {nodeState.output.slice(0, 60)}
        </p>
      )}

      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-2 !border-gray-400 !bg-white"
      />
    </div>
  )
}

/** 不同节点类型的配置摘要 */
function NodeSummary({ type, config }: { type: NodeType; config: Record<string, unknown> }) {
  if (type === "llm") {
    const model = (config.model as string) || "default"
    const prompt = (config.system_prompt as string) || ""
    return (
      <div className="mt-0.5 text-xs text-gray-400 space-y-0.5">
        <p>模型: {model}</p>
        {prompt && <p className="truncate">系统: {prompt.slice(0, 30)}</p>}
      </div>
    )
  }
  if (type === "retrieval") {
    const topK = (config.top_k as number) || 5
    return <p className="mt-0.5 text-xs text-gray-400">Top-K: {topK}</p>
  }
  if (type === "condition") {
    const expr = (config.expression as string) || ""
    return (
      <p className="mt-0.5 text-xs text-gray-400 truncate" title={expr}>
        {expr || "未配置条件"}
      </p>
    )
  }
  if (type === "notify") {
    const channels = (config.channels as unknown[]) || []
    return <p className="mt-0.5 text-xs text-gray-400">{channels.length} 渠道</p>
  }
  if (type === "memory") {
    const action = (config.action as string) || "save"
    const key = (config.key as string) || ""
    return (
      <p className="mt-0.5 text-xs text-gray-400 truncate">
        {action === "save" ? "写入" : "读取"}: {key || "未设置"}
      </p>
    )
  }
  // text
  const template = (config.template as string) || ""
  return (
    <p className="mt-0.5 text-xs text-gray-400 truncate" title={template}>
      {template || "空模板"}
    </p>
  )
}

export const LLMNode = memo(BaseNode)
export const RetrievalNode = memo(BaseNode)
export const ConditionNode = memo(BaseNode)
export const TextNode = memo(BaseNode)
export const NotifyNode = memo(BaseNode)
export const MemoryNode = memo(BaseNode)

export const nodeTypes = {
  llm: LLMNode,
  retrieval: RetrievalNode,
  condition: ConditionNode,
  text: TextNode,
  notify: NotifyNode,
  memory: MemoryNode,
}
