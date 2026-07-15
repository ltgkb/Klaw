import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react"
import { useParams, useNavigate } from "react-router-dom"
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Connection,
  type Node,
  type Edge,
  BackgroundVariant,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import {
  ArrowLeft,
  Save,
  Play,
  Loader2,
  History,
} from "lucide-react"
import { flowApi, type FlowRead, type NodeType, type ExecutionRead, type NodeState } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NodeToolbox } from "@/components/flow/NodeToolbox"
import { NodeConfigPanel } from "@/components/flow/NodeConfigPanel"
import { nodeTypes } from "@/components/flow/nodes"
import { cn } from "@/lib/utils"

let nodeIdCounter = 0
function genNodeId() {
  nodeIdCounter += 1
  return `node-${Date.now().toString(36)}-${nodeIdCounter}`
}

const DEFAULT_CONFIGS: Record<NodeType, Record<string, unknown>> = {
  llm: { model: "default", system_prompt: "", user_template: "{input}" },
  retrieval: { kb_id: "", query_template: "{input}", top_k: 5 },
  condition: { expression: "{input} == ''" },
  text: { template: "" },
  notify: { title_template: "Agent 通知", content_template: "{input}", channels: [] },
  memory: { action: "save", key: "", value_template: "{input}", session_id: "" },
}

const NODE_LABELS: Record<NodeType, string> = {
  llm: "LLM 对话",
  retrieval: "知识库检索",
  condition: "条件分支",
  text: "文本拼接",
  notify: "消息推送",
  memory: "记忆读写",
}

function FlowCanvasInner() {
  const { flowId } = useParams<{ flowId: string }>()
  const navigate = useNavigate()

  const [flow, setFlow] = useState<FlowRead | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [executing, setExecuting] = useState(false)

  // 执行输入
  const [execInput, setExecInput] = useState("")

  // XYFlow 状态
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  // 执行状态
  const [execution, setExecution] = useState<ExecutionRead | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  // ── 加载工作流 ──
  const fetchFlow = useCallback(async () => {
    if (!flowId) return
    setLoading(true)
    try {
      const resp = await flowApi.get(flowId)
      setFlow(resp.data)
      const dag = resp.data.dag || { nodes: [], edges: [] }
      // 转换为 XYFlow 格式 (后端节点 data 里没有 nodeState)
      setNodes(dag.nodes.map((n) => ({ ...n })) as Node[])
      setEdges(dag.edges.map((e) => ({ ...e })) as Edge[])
    } catch {
      // 错误由拦截器处理
    } finally {
      setLoading(false)
    }
  }, [flowId, setNodes, setEdges])

  useEffect(() => {
    fetchFlow()
  }, [fetchFlow])

  // ── SSE 清理 ──
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close()
    }
  }, [])

  // ── 添加节点 ──
  const handleAddNode = useCallback((type: NodeType) => {
    const id = genNodeId()
    const newNode: Node = {
      id,
      type,
      position: {
        x: 200 + Math.random() * 100,
        y: 150 + Math.random() * 80,
      },
      data: {
        label: NODE_LABELS[type],
        config: { ...DEFAULT_CONFIGS[type] },
      },
    }
    setNodes((nds) => [...nds, newNode])
    setSelectedNodeId(id)
  }, [setNodes])

  // ── 连线 ──
  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) => addEdge({ ...connection, id: `e-${connection.source}-${connection.target}` }, eds))
    },
    [setEdges],
  )

  // ── 选中节点 ──
  const onNodeClick = useCallback((_: MouseEvent, node: Node) => {
    setSelectedNodeId(node.id)
  }, [])

  // ── 点击空白取消选中 ──
  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null)
  }, [])

  // ── 节点数据变更 ──
  const handleNodeDataChange = useCallback((id: string, newData: Partial<Node["data"]>) => {
    setNodes((nds) =>
      nds.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, ...newData } } : n,
      ),
    )
  }, [setNodes])

  // ── 删除节点 ──
  const handleDeleteNode = useCallback((id: string) => {
    setNodes((nds) => nds.filter((n) => n.id !== id))
    setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id))
    setSelectedNodeId(null)
  }, [setNodes, setEdges])

  // ── 保存 DAG ──
  const handleSave = async () => {
    if (!flowId) return
    setSaving(true)
    try {
      const dag = {
        nodes: nodes.map((n) => ({
          id: n.id,
          type: n.type as NodeType,
          position: n.position,
          data: { label: (n.data as { label: string }).label, config: (n.data as { config: Record<string, unknown> }).config },
        })),
        edges: edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
        })),
      }
      await flowApi.update(flowId, { dag })
      await fetchFlow()
    } catch {
      // 错误由拦截器处理
    } finally {
      setSaving(false)
    }
  }

  // ── 执行工作流 ──
  const handleExecute = async () => {
    if (!flowId) return
    // 先保存再执行
    setSaving(true)
    try {
      const dag = {
        nodes: nodes.map((n) => ({
          id: n.id,
          type: n.type as NodeType,
          position: n.position,
          data: { label: (n.data as { label: string }).label, config: (n.data as { config: Record<string, unknown> }).config },
        })),
        edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
      }
      await flowApi.update(flowId, { dag })
    } catch {
      setSaving(false)
      return
    }
    setSaving(false)

    setExecuting(true)
    setExecution(null)
    try {
      // 解析执行输入 JSON
      let input: Record<string, unknown> = {}
      if (execInput.trim()) {
        try {
          input = JSON.parse(execInput)
        } catch {
          // 不是 JSON, 当作 {input: "text"}
          input = { input: execInput.trim() }
        }
      }
      const resp = await flowApi.execute(flowId, input)
      const execId = resp.data.execution_id

      // SSE 连接
      const token = localStorage.getItem("access_token")
      eventSourceRef.current?.close()
      const es = new EventSource(
        `/api/v1/agent-flows/${flowId}/executions/${execId}/stream?token=${token}`,
      )
      eventSourceRef.current = es

      es.addEventListener("progress", (ev) => {
        try {
          const data = JSON.parse((ev as MessageEvent).data)
          setExecution(data)
          // 更新节点状态
          updateNodeStates(data.node_states || {})
        } catch {
          // 忽略解析错误
        }
      })

      es.addEventListener("complete", (ev) => {
        try {
          const data = JSON.parse((ev as MessageEvent).data)
          setExecution(data)
          updateNodeStates(data.node_states || {})
        } catch {
          // 忽略解析错误
        }
        es.close()
        eventSourceRef.current = null
        setExecuting(false)
      })

      es.addEventListener("error", (ev) => {
        try {
          const data = JSON.parse((ev as MessageEvent).data)
          setExecution(data)
        } catch {
          // 连接错误
        }
        es.close()
        eventSourceRef.current = null
        setExecuting(false)
      })

      // SSE 也可能因网络错误关闭
      es.onerror = () => {
        es.close()
        eventSourceRef.current = null
        setExecuting(false)
        // 兜底: 轮询获取最终状态
        pollExecution(flowId, execId)
      }
    } catch {
      setExecuting(false)
    }
  }

  // ── SSE 断开时兜底轮询 ──
  const pollExecution = async (fid: string, eid: string) => {
    for (let i = 0; i < 30; i++) {
      try {
        const resp = await flowApi.getExecution(fid, eid)
        setExecution(resp.data)
        updateNodeStates(resp.data.node_states || {})
        if (["success", "failed", "cancelled"].includes(resp.data.status)) break
      } catch {
        break
      }
      await new Promise((r) => setTimeout(r, 1000))
    }
    setExecuting(false)
  }

  // ── 更新节点执行状态 (高亮) ──
  const updateNodeStates = useCallback((nodeStates: Record<string, NodeState>) => {
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: { ...n.data, nodeState: nodeStates[n.id] },
      })),
    )
  }, [setNodes])

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) || null

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!flow) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/flows")}>
          <ArrowLeft className="h-4 w-4" />
          返回
        </Button>
        <p className="text-sm text-muted-foreground">工作流不存在</p>
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* 顶部工具栏 */}
      <div className="flex items-center gap-3 border-b px-4 py-2">
        <Button variant="ghost" size="sm" onClick={() => navigate("/flows")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1">
          <h1 className="text-base font-semibold">{flow.name}</h1>
          <p className="text-xs text-muted-foreground">
            {flow.description || "无描述"} · {nodes.length} 节点 · {edges.length} 连线
          </p>
        </div>

        {/* 执行输入 */}
        <div className="flex items-center gap-2">
          <Input
            className="h-8 w-48 text-xs"
            value={execInput}
            onChange={(e) => setExecInput(e.target.value)}
            placeholder='输入文本或 {"key":"val"}'
            disabled={executing}
          />
        </div>

        <Button variant="outline" size="sm" onClick={handleSave} disabled={saving || executing}>
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          保存
        </Button>
        <Button size="sm" onClick={handleExecute} disabled={executing || saving}>
          {executing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          执行
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate(`/flows/${flowId}/executions`)}
        >
          <History className="h-4 w-4" />
          历史
        </Button>
      </div>

      {/* 执行状态条 */}
      {execution && (
        <div className={cn(
          "flex items-center gap-2 px-4 py-1.5 text-xs",
          execution.status === "success" && "bg-green-50 text-green-700",
          execution.status === "failed" && "bg-red-50 text-red-700",
          execution.status === "running" && "bg-blue-50 text-blue-700",
          execution.status === "paused" && "bg-amber-50 text-amber-700",
        )}>
          <span className="font-medium">执行状态: {execution.status}</span>
          {execution.error_message && (
            <span className="truncate">— {execution.error_message}</span>
          )}
        </div>
      )}

      {/* 画布区域 */}
      <div className="flex flex-1 overflow-hidden">
        <NodeToolbox onAdd={handleAddNode} />

        {/* XYFlow 画布 */}
        <div className="flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            fitView
            className="bg-secondary/10"
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
            <Controls />
            <MiniMap
              className="!rounded-lg !border"
              nodeColor={(n) => {
                const state = (n.data as { nodeState?: NodeState })?.nodeState?.status
                if (state === "success") return "#22c55e"
                if (state === "running") return "#3b82f6"
                if (state === "failed") return "#ef4444"
                return "#d1d5db"
              }}
            />
          </ReactFlow>
        </div>

        {/* 右侧配置面板 */}
        <div className="w-72 border-l bg-background">
          <NodeConfigPanel
            node={selectedNode}
            onChange={handleNodeDataChange}
            onDelete={handleDeleteNode}
          />
        </div>
      </div>
    </div>
  )
}

export function FlowCanvas() {
  return (
    <ReactFlowProvider>
      <FlowCanvasInner />
    </ReactFlowProvider>
  )
}
