import { memo, useLayoutEffect } from "react"
import {
  Handle,
  NodeResizer,
  Position,
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  useReactFlow,
  useUpdateNodeInternals,
  type NodeProps,
  type EdgeProps,
} from "@xyflow/react"
import { Brain, Database, GitBranch, Type, Bell, BrainCog, Play, Repeat2, Square } from "lucide-react"
import { cn } from "@/lib/utils"
import type { NodeType, NodeState } from "@/lib/api"

/** 节点类型 → 图标 + 颜色 */
const NODE_META: Record<NodeType, { icon: typeof Brain; color: string; label: string }> = {
  start: { icon: Play, color: "border-green-500 bg-green-50", label: "开始" },
  end: { icon: Square, color: "border-red-400 bg-red-50", label: "结束" },
  llm: { icon: Brain, color: "border-blue-400 bg-blue-50", label: "LLM 对话" },
  retrieval: { icon: Database, color: "border-purple-400 bg-purple-50", label: "知识库检索" },
  condition: { icon: GitBranch, color: "border-amber-400 bg-amber-50", label: "条件分支" },
  loop: { icon: Repeat2, color: "border-cyan-400 bg-cyan-50", label: "循环" },
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
  const t = (type as NodeType) ?? "text"
  const meta = NODE_META[t] ?? NODE_META.text
  const Icon = meta.icon
  const nodeState = nodeData.nodeState
  const stateClass = nodeState?.status ? STATE_BORDER[nodeState.status] ?? "" : ""
  const isStart = t === "start"
  const isEnd = t === "end"
  const isCondition = t === "condition"
  const conditionCases = (nodeData.config?.cases as { id?: string; name?: string }[] | undefined) || []
  const updateNodeInternals = useUpdateNodeInternals()
  const handleSignature = conditionCases.map((item) => item.id).join("|")

  useLayoutEffect(() => {
    const frame = requestAnimationFrame(() => updateNodeInternals(id))
    return () => cancelAnimationFrame(frame)
  }, [handleSignature, id, updateNodeInternals])

  return (
    <div
      className={cn(
        "relative h-full min-h-[84px] w-full min-w-[180px] rounded-lg border-2 px-3 py-2 shadow-sm transition-shadow",
        meta.color,
        stateClass,
        selected && "ring-2 ring-primary",
      )}
    >
      <NodeResizer
        isVisible={selected}
        minWidth={180}
        minHeight={isCondition ? Math.max(116, 92 + conditionCases.length * 24) : 84}
        maxWidth={480}
        maxHeight={420}
        color="#2563eb"
      />

      {/* 输入 Handle (开始节点无) */}
      {!isStart && (
        <Handle
          type="target"
          position={Position.Left}
          className="!h-3 !w-3 !border-2 !border-gray-400 !bg-white"
        />
      )}

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

      {/* 条件分支: 多个 source handle (每个 case 一个) + 默认 */}
      {isCondition && conditionCases.length ? (
        <div className="mt-2 space-y-1">
          {conditionCases.map((c, i) => (
            <div
              key={c.id || i}
              className="relative flex items-center justify-end gap-1 rounded bg-white/70 px-2 py-0.5 text-[11px] text-gray-600"
            >
              <span className="truncate">{c.name || c.id || `分支${i + 1}`}</span>
              <Handle
                type="source"
                position={Position.Right}
                id={c.id}
                className="!absolute !right-[-6px] !h-2.5 !w-2.5 !border-2 !border-amber-500 !bg-white"
                style={{ top: "50%", transform: "translateY(-50%)" }}
              />
            </div>
          ))}
          <div className="relative flex items-center justify-end gap-1 rounded bg-white/70 px-2 py-0.5 text-[11px] text-gray-500">
            <span>{(nodeData.config?.default_name as string) || "默认"}</span>
            <Handle
              type="source"
              position={Position.Right}
              id="default"
              className="!absolute !right-[-6px] !h-2.5 !w-2.5 !border-2 !border-gray-400 !bg-white"
              style={{ top: "50%", transform: "translateY(-50%)" }}
            />
          </div>
        </div>
      ) : (
        <Handle
          type="source"
          position={Position.Right}
          className="!h-3 !w-3 !border-2 !border-gray-400 !bg-white"
          isConnectable={!isEnd}
        />
      )}
    </div>
  )
}

/** 不同节点类型的配置摘要 */
function NodeSummary({ type, config }: { type: NodeType; config: Record<string, unknown> }) {
  if (type === "start") {
    const inputs = (config.inputs as { name?: string }[]) || []
    if (inputs.length === 0) return <p className="mt-0.5 text-xs text-gray-400">输入: {`{input}`}</p>
    return (
      <p className="mt-0.5 text-xs text-gray-400 truncate">
        输入: {inputs.map((i) => i.name || "?").filter(Boolean).join(", ")}
      </p>
    )
  }
  if (type === "end") {
    const out = (config.output as string) || ""
    return (
      <p className="mt-0.5 text-xs text-gray-400 truncate">
        {out ? `输出: ${out}` : "输出: 最后节点"}
      </p>
    )
  }
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
    const cases = (config.cases as unknown[]) || []
    return <p className="mt-0.5 text-xs text-gray-400">{cases.length} 个分支</p>
  }
  if (type === "loop") {
    const maxIterations = (config.max_iterations as number) || 20
    return <p className="mt-0.5 text-xs text-gray-400">最多 {maxIterations} 次</p>
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

export const StartNode = memo(BaseNode)
export const EndNode = memo(BaseNode)
export const LLMNode = memo(BaseNode)
export const RetrievalNode = memo(BaseNode)
export const ConditionNode = memo(BaseNode)
export const LoopNode = memo(BaseNode)
export const TextNode = memo(BaseNode)
export const NotifyNode = memo(BaseNode)
export const MemoryNode = memo(BaseNode)

export const nodeTypes = {
  start: StartNode,
  end: EndNode,
  llm: LLMNode,
  retrieval: RetrievalNode,
  condition: ConditionNode,
  loop: LoopNode,
  text: TextNode,
  notify: NotifyNode,
  memory: MemoryNode,
}

/** 可删除的连线: 中点显示 × 按钮, 点击删除; 选中后高亮 */
function DeletableEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  selected,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })
  const { setEdges } = useReactFlow()
  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{ stroke: selected ? "#3b82f6" : "#9ca3af", strokeWidth: selected ? 2.5 : 1.5 }}
      />
      <EdgeLabelRenderer>
        <button
          className="nodrag nopan flex h-5 w-5 items-center justify-center rounded-full border border-gray-300 bg-white text-xs text-gray-500 shadow hover:bg-red-50 hover:text-red-600"
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: "all",
          }}
          title="删除连线"
          onClick={() => setEdges((eds) => eds.filter((e) => e.id !== id))}
        >
          ×
        </button>
      </EdgeLabelRenderer>
    </>
  )
}

export const edgeTypes = { deletable: DeletableEdge }
