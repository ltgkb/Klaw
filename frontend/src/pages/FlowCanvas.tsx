import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react"
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
  useReactFlow,
  type Connection,
  type Node,
  type Edge,
  type NodeTypes,
  type OnConnectStart,
  type OnConnectEnd,
  BackgroundVariant,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import {
  ArrowLeft,
  Save,
  Play,
  Loader2,
  History,
  Download,
  Upload,
  Brain,
  Database,
  GitBranch,
  Type,
  Bell,
  BrainCog,
  Repeat2,
  Square,
  Globe,
  GripVertical,
  Home,
} from "lucide-react"
import {
  flowApi,
  systemApi,
  type FlowRead,
  type NodeType,
  type ExecutionRead,
  type ExecutionStreamPayload,
  type NodeState,
} from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NodeToolbox } from "@/components/flow/NodeToolbox"
import { NodeConfigPanel } from "@/components/flow/NodeConfigPanel"
import { nodeTypes, edgeTypes, type CanvasNodeType } from "@/components/flow/nodes"
import { cn } from "@/lib/utils"

let nodeIdCounter = 0
const DEFAULT_NODE_WIDTH = 220
const DEFAULT_NODE_HEIGHT = 96
const TOOLBOX_WIDTH_KEY = "claw-flow-toolbox-width"
const CONFIG_WIDTH_KEY = "claw-flow-config-width"

function genNodeId() {
  nodeIdCounter += 1
  return `node-${Date.now().toString(36)}-${nodeIdCounter}`
}

/** 连线 id: 含 sourceHandle, 避免条件分支多条出边 id 冲突 */
function genEdgeId(source: string, sourceHandle: string | null | undefined, target: string) {
  return `e-${source}:${sourceHandle ?? ""}-${target}`
}

/** 序列化连线: 保留 sourceHandle/targetHandle (后端条件分支路由依赖 sourceHandle) */
function serializeEdge(e: Edge) {
  return {
    id: e.id,
    source: e.source,
    target: e.target,
    sourceHandle: e.sourceHandle ?? null,
    targetHandle: e.targetHandle ?? null,
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function defaultNodeHeight(type: string | undefined, config: Record<string, unknown>) {
  if (type !== "condition") return DEFAULT_NODE_HEIGHT
  const cases = Array.isArray(config.cases) ? config.cases.length : 0
  return Math.max(116, 92 + cases * 24)
}

function initialNodeStyle(node: Pick<Node, "type" | "data" | "style">) {
  const config = (node.data as { config?: Record<string, unknown> }).config || {}
  return {
    width: DEFAULT_NODE_WIDTH,
    height: defaultNodeHeight(node.type, config),
    ...node.style,
  }
}

function readStoredWidth(key: string, fallback: number) {
  const value = Number(localStorage.getItem(key))
  return Number.isFinite(value) && value > 0 ? value : fallback
}

/** 序列化节点: 保留测量/调整后的宽高 (deploy 侧画布尺寸稳定化) */
function serializeNode(node: Node) {
  const styleWidth = typeof node.style?.width === "number" ? node.style.width : undefined
  const styleHeight = typeof node.style?.height === "number" ? node.style.height : undefined
  const width = node.width ?? styleWidth ?? DEFAULT_NODE_WIDTH
  const height = node.height ?? styleHeight
  return {
    id: node.id,
    type: node.type as NodeType,
    position: node.position,
    style: { width, ...(height ? { height } : {}) },
    data: {
      label: (node.data as { label: string }).label,
      config: (node.data as { config: Record<string, unknown> }).config,
    },
  }
}

interface PanelResizeHandleProps {
  label: string
  value: number
  min: number
  max: number
  direction: 1 | -1
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void
  onNudge: (delta: number) => void
}

function PanelResizeHandle({ label, value, min, max, direction, onPointerDown, onNudge }: PanelResizeHandleProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return
    event.preventDefault()
    const screenDelta = event.key === "ArrowRight" ? 16 : -16
    onNudge(screenDelta * direction)
  }

  return (
    <div
      role="separator"
      aria-label={label}
      aria-orientation="vertical"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={Math.round(value)}
      tabIndex={0}
      className="group relative z-20 flex w-2 shrink-0 cursor-col-resize touch-none items-center justify-center border-x bg-muted/30 outline-none hover:bg-accent focus-visible:bg-accent"
      onPointerDown={onPointerDown}
      onKeyDown={handleKeyDown}
    >
      <GripVertical className="h-4 w-4 text-muted-foreground opacity-70 group-hover:opacity-100 group-focus:opacity-100" />
    </div>
  )
}

const DEFAULT_CONFIGS: Record<CanvasNodeType, Record<string, unknown>> = {
  start: { template: "{input}" },
  end: { template: "" },
  llm: { model: "default", system_prompt: "", user_template: "{input}" },
  retrieval: { kb_id: "", query_template: "{input}", top_k: 5 },
  condition: { cases: [{ id: "case1", name: "条件1", expression: "{input} == ''" }], default_name: "默认" },
  loop: { items_template: "{input}", body_node_id: "", item_variable: "item", index_variable: "index", max_iterations: 20, continue_on_error: false },
  text: { template: "" },
  notify: { title_template: "Agent 通知", content_template: "{input}", channels: [] },
  memory: { action: "save", key: "", value_template: "{input}", session_id: "" },
  http: { method: "GET", url: "", headers: {}, body: "", timeout_s: 30 },
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
}

// 拖线弹出菜单可添加的节点 (不含 start, start 是入口)
const ADDABLE_TYPES: { type: CanvasNodeType; label: string; icon: typeof Brain }[] = [
  { type: "end", label: "结束", icon: Square },
  { type: "llm", label: "LLM 对话", icon: Brain },
  { type: "retrieval", label: "知识库检索", icon: Database },
  { type: "condition", label: "条件分支", icon: GitBranch },
  { type: "loop", label: "循环", icon: Repeat2 },
  { type: "text", label: "文本拼接", icon: Type },
  { type: "notify", label: "消息推送", icon: Bell },
  { type: "memory", label: "记忆读写", icon: BrainCog },
  { type: "http", label: "HTTP 请求", icon: Globe },
]

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
  const [toolboxWidth, setToolboxWidth] = useState(() => clamp(readStoredWidth(TOOLBOX_WIDTH_KEY, 176), 140, 320))
  const [configWidth, setConfigWidth] = useState(() => clamp(readStoredWidth(CONFIG_WIDTH_KEY, 288), 260, 520))

  // 执行状态
  const [execution, setExecution] = useState<ExecutionRead | ExecutionStreamPayload | null>(null)
  const streamAbortRef = useRef<AbortController | null>(null)

  // 系统默认 LLM 模型 (新建 LLM 节点默认使用)
  const [defaultLlmModel, setDefaultLlmModel] = useState("")
  useEffect(() => {
    systemApi.getLlmDefault().then((r) => setDefaultLlmModel(r.data.default_model || "")).catch(() => {})
  }, [])

  // 拖线弹出节点菜单
  const { screenToFlowPosition } = useReactFlow()
  const connectingNodeId = useRef<string | null>(null)
  const connectingHandleId = useRef<string | null>(null)
  const canvasRef = useRef<HTMLDivElement | null>(null)
  const [addMenu, setAddMenu] = useState<{ open: boolean; x: number; y: number }>({ open: false, x: 0, y: 0 })
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // ── 加载工作流 ──
  const fetchFlow = useCallback(async () => {
    if (!flowId) return
    setLoading(true)
    try {
      const resp = await flowApi.get(flowId)
      setFlow(resp.data)
      const dag = resp.data.dag || { nodes: [], edges: [] }
      // 转换为 XYFlow 格式 (后端节点 data 里没有 nodeState)
      setNodes(dag.nodes.map((n) => ({ ...n, style: initialNodeStyle(n as Node) })) as Node[])
      setEdges(dag.edges.map((e) => ({ ...e, type: "deletable" })) as Edge[])
    } catch {
      // 错误由拦截器处理
    } finally {
      setLoading(false)
    }
  }, [flowId, setNodes, setEdges])

  useEffect(() => {
    fetchFlow()
  }, [fetchFlow])

  // ── SSE 清理 + 卸载标记 (P2-9: 兜底轮询在卸载后不再 setState) ──
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      streamAbortRef.current?.abort()
    }
  }, [])

  const startPanelResize = useCallback((panel: "toolbox" | "config", event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    event.preventDefault()
    const startX = event.clientX
    const startWidth = panel === "toolbox" ? toolboxWidth : configWidth
    const min = panel === "toolbox" ? 140 : 260
    const max = panel === "toolbox" ? 320 : 520
    const direction = panel === "toolbox" ? 1 : -1
    const previousCursor = document.body.style.cursor
    const previousUserSelect = document.body.style.userSelect
    document.body.style.cursor = "col-resize"
    document.body.style.userSelect = "none"
    let pendingFrame: number | null = null
    let pendingClientX = startX

    const applyWidth = (clientX: number) => {
      const width = clamp(startWidth + (clientX - startX) * direction, min, max)
      if (panel === "toolbox") setToolboxWidth(width)
      else setConfigWidth(width)
    }
    const handlePointerMove = (moveEvent: PointerEvent) => {
      pendingClientX = moveEvent.clientX
      if (pendingFrame !== null) return
      pendingFrame = requestAnimationFrame(() => {
        pendingFrame = null
        applyWidth(pendingClientX)
      })
    }
    const handlePointerUp = (upEvent: PointerEvent) => {
      if (pendingFrame !== null) cancelAnimationFrame(pendingFrame)
      applyWidth(upEvent.clientX)
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
      document.body.style.cursor = previousCursor
      document.body.style.userSelect = previousUserSelect
      const width = clamp(startWidth + (upEvent.clientX - startX) * direction, min, max)
      localStorage.setItem(panel === "toolbox" ? TOOLBOX_WIDTH_KEY : CONFIG_WIDTH_KEY, String(Math.round(width)))
    }
    window.addEventListener("pointermove", handlePointerMove)
    window.addEventListener("pointerup", handlePointerUp, { once: true })
  }, [configWidth, toolboxWidth])

  const nudgePanel = useCallback((panel: "toolbox" | "config", delta: number) => {
    if (panel === "toolbox") {
      setToolboxWidth((current) => {
        const next = clamp(current + delta, 140, 320)
        localStorage.setItem(TOOLBOX_WIDTH_KEY, String(Math.round(next)))
        return next
      })
    } else {
      setConfigWidth((current) => {
        const next = clamp(current + delta, 260, 520)
        localStorage.setItem(CONFIG_WIDTH_KEY, String(Math.round(next)))
        return next
      })
    }
  }, [])

  const nodePositionAt = useCallback((point?: { x: number; y: number }) => {
    const rect = canvasRef.current?.getBoundingClientRect()
    const screenPoint = point || (rect ? {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
    } : { x: window.innerWidth / 2, y: window.innerHeight / 2 })
    const flowPoint = screenToFlowPosition(screenPoint)
    return {
      x: flowPoint.x - DEFAULT_NODE_WIDTH / 2,
      y: flowPoint.y - DEFAULT_NODE_HEIGHT / 2,
    }
  }, [screenToFlowPosition])

  // ── 添加节点 ──
  const handleAddNode = useCallback((type: CanvasNodeType) => {
    const id = genNodeId()
    const config = { ...DEFAULT_CONFIGS[type] }
    if (type === "llm" && defaultLlmModel) config.model = defaultLlmModel
    const newNode: Node = {
      id,
      type,
      position: nodePositionAt(),
      style: { width: DEFAULT_NODE_WIDTH, height: defaultNodeHeight(type, config) },
      data: {
        label: NODE_LABELS[type],
        config,
      },
    }
    setNodes((nds) => [...nds.map((node) => ({ ...node, selected: false })), { ...newNode, selected: true }])
    setSelectedNodeId(id)
  }, [setNodes, defaultLlmModel, nodePositionAt])

  // ── 连线 ──
  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: genEdgeId(connection.source, connection.sourceHandle, connection.target),
            type: "deletable",
          },
          eds,
        ),
      )
    },
    [setEdges],
  )

  // ── 拖线开始: 记录源节点与源 handle (条件分支需保留 sourceHandle) ──
  const onConnectStart = useCallback<OnConnectStart>((_, { nodeId, handleId }) => {
    connectingNodeId.current = nodeId
    connectingHandleId.current = handleId
  }, [])

  // ── 拖线结束: 若松开在空白处, 弹出节点菜单 ──
  const onConnectEnd = useCallback<OnConnectEnd>((event) => {
    const sourceId = connectingNodeId.current
    if (!sourceId) {
      connectingHandleId.current = null
      return
    }
    const target = event.target as HTMLElement | null
    const isPane = !!target?.classList?.contains("react-flow__pane")
    if (!isPane) {
      connectingNodeId.current = null
      connectingHandleId.current = null
      return
    }
    const e = event as unknown as {
      changedTouches?: { clientX: number; clientY: number }[]
      clientX?: number
      clientY?: number
    }
    const point =
      e.changedTouches && e.changedTouches.length
        ? { x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY }
        : { x: e.clientX ?? 0, y: e.clientY ?? 0 }
    setAddMenu({ open: true, x: point.x, y: point.y })
  }, [])

  // ── 从菜单添加节点并自动连线 ──
  const handleAddNodeFromMenu = useCallback((type: CanvasNodeType) => {
    const sourceId = connectingNodeId.current
    const sourceHandle = connectingHandleId.current
    const position = nodePositionAt({ x: addMenu.x, y: addMenu.y })
    const id = genNodeId()
    const config = { ...DEFAULT_CONFIGS[type] }
    if (type === "llm" && defaultLlmModel) config.model = defaultLlmModel
    const newNode: Node = {
      id,
      type,
      position,
      style: { width: DEFAULT_NODE_WIDTH, height: defaultNodeHeight(type, config) },
      data: { label: NODE_LABELS[type], config },
    }
    setNodes((nds) => [...nds.map((node) => ({ ...node, selected: false })), { ...newNode, selected: true }])
    if (sourceId) {
      setEdges((eds) =>
        addEdge(
          {
            source: sourceId,
            sourceHandle,
            target: id,
            id: genEdgeId(sourceId, sourceHandle, id),
            type: "deletable",
          },
          eds,
        ),
      )
    }
    setSelectedNodeId(id)
    setAddMenu({ open: false, x: 0, y: 0 })
    connectingNodeId.current = null
    connectingHandleId.current = null
  }, [addMenu.x, addMenu.y, nodePositionAt, setEdges, setNodes, defaultLlmModel])

  // ── 选中节点 ──
  const onNodeClick = useCallback((_: MouseEvent, node: Node) => {
    setSelectedNodeId(node.id)
    setAddMenu({ open: false, x: 0, y: 0 })
  }, [])

  // ── 点击空白取消选中 + 关闭菜单 ──
  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null)
    setAddMenu({ open: false, x: 0, y: 0 })
    connectingNodeId.current = null
    connectingHandleId.current = null
  }, [])

  // ── 节点数据变更 ──
  const handleNodeDataChange = useCallback((id: string, newData: Partial<Node["data"]>) => {
    const nextConfig = (newData as { config?: Record<string, unknown> }).config
    if (nextConfig && Array.isArray(nextConfig.cases)) {
      const validHandles = new Set([
        "default",
        ...nextConfig.cases.map((item) => String((item as { id?: string }).id || "")).filter(Boolean),
      ])
      setEdges((current) => current.filter((edge) => (
        edge.source !== id || !edge.sourceHandle || validHandles.has(edge.sourceHandle)
      )))
    }
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id !== id) return node
        const updated = { ...node, data: { ...node.data, ...newData } }
        if (nextConfig && Array.isArray(nextConfig.cases)) {
          const minHeight = Math.max(116, 92 + nextConfig.cases.length * 24)
          const currentHeight = node.height ?? (typeof node.style?.height === "number" ? node.style.height : 0)
          if (currentHeight < minHeight) updated.style = { ...node.style, height: minHeight }
        }
        return updated
      }),
    )
  }, [setEdges, setNodes])

  // ── 删除节点 ──
  const handleDeleteNode = useCallback((id: string) => {
    setNodes((nds) =>
      nds
        .filter((n) => n.id !== id)
        .map((n) => {
          if (n.type !== "loop") return n
          const data = n.data as { label: string; config: Record<string, unknown> }
          if (data.config.body_node_id !== id) return n
          return { ...n, data: { ...data, config: { ...data.config, body_node_id: "" } } }
        }),
    )
    setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id))
    setSelectedNodeId(null)
  }, [setNodes, setEdges])

  // ── 保存 DAG ──
  const handleSave = async () => {
    if (!flowId) return
    setSaving(true)
    try {
      const dag = {
        nodes: nodes.map(serializeNode),
        edges: edges.map(serializeEdge),
      }
      await flowApi.update(flowId, { dag })
      await fetchFlow()
    } catch {
      // 错误由拦截器处理
    } finally {
      setSaving(false)
    }
  }

  // ── 导出画布为 JSON (对标 RAGFlow agent 导出) ──
  const handleExport = () => {
    const data = {
      app: "claw-agent",
      version: 1,
      name: flow?.name || "agent",
      exported_at: new Date().toISOString(),
      nodes: nodes.map(serializeNode),
      edges: edges.map(serializeEdge),
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${flow?.name || "agent"}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  // ── 导入画布 JSON ──
  const handleImportFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file || !flowId) return
    const text = await file.text()
    let parsed: { nodes?: Node[]; edges?: Edge[]; dag?: { nodes?: Node[]; edges?: Edge[] } }
    try {
      parsed = JSON.parse(text)
    } catch {
      alert("JSON 解析失败，请检查文件格式")
      return
    }
    const impNodes = parsed.nodes || parsed.dag?.nodes || []
    const impEdges = parsed.edges || parsed.dag?.edges || []
    if (!impNodes.length) {
      alert("文件中未找到节点")
      return
    }
    // 重新生成节点 id, 避免与现有节点冲突; 重映射边
    const idMap: Record<string, string> = {}
    for (const n of impNodes) idMap[n.id] = genNodeId()
    const newNodes: Node[] = impNodes.map((n) => {
      const data = n.data as { label?: string; config?: Record<string, unknown> }
      const config = { ...(data?.config || {}) }
      if (n.type === "loop" && typeof config.body_node_id === "string") {
        config.body_node_id = idMap[config.body_node_id] || ""
      }
      const importedNode = { ...n, data: { ...data, config } }
      return {
        ...importedNode,
        id: idMap[n.id],
        style: initialNodeStyle(importedNode),
      }
    })
    const newEdges: Edge[] = impEdges.map((edge) => {
      const s = idMap[edge.source] || edge.source
      const t = idMap[edge.target] || edge.target
      return { ...edge, id: genEdgeId(s, edge.sourceHandle, t), source: s, target: t }
    })
    setNodes(newNodes)
    setEdges(newEdges)
    // 自动保存
    setSaving(true)
    try {
      const dag = {
        nodes: newNodes.map(serializeNode),
        edges: newEdges.map(serializeEdge),
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
        nodes: nodes.map(serializeNode),
        edges: edges.map(serializeEdge),
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
      // 解析执行输入: 优先顶部输入框, 为空时取「开始」节点的命名输入变量
      let input: Record<string, unknown> = {}
      if (execInput.trim()) {
        try {
          input = JSON.parse(execInput)
        } catch {
          // 不是 JSON, 当作 {input: "text"}
          input = { input: execInput.trim() }
        }
      } else {
        const startNode = nodes.find((n) => n.type === "start")
        const inputs =
          (startNode?.data as { config?: { inputs?: { name?: string; value?: string }[] } } | undefined)?.config
            ?.inputs || []
        if (inputs.length) {
          for (const i of inputs) {
            if (i.name) input[i.name] = i.value || ""
          }
          const firstVal = inputs.find((i) => i.value)?.value || ""
          input["input"] = firstVal
          input["sys.query"] = firstVal
        }
      }
      const resp = await flowApi.execute(flowId, input)
      const execId = resp.data.execution_id

      streamAbortRef.current?.abort()
      streamAbortRef.current = flowApi.streamExecution(flowId, execId, {
        onProgress: (data) => {
          if (!mountedRef.current) return
          setExecution(data)
          updateNodeStates(data.node_states || {})
        },
        onComplete: (data) => {
          if (!mountedRef.current) return
          setExecution(data)
          updateNodeStates(data.node_states || {})
          streamAbortRef.current = null
          setExecuting(false)
        },
        onError: () => {
          if (!mountedRef.current) return
          streamAbortRef.current = null
          void pollExecution(flowId, execId)
        },
      })
    } catch {
      setExecuting(false)
    }
  }

  // ── SSE 断开时兜底轮询 (P2-9: 组件卸载后立即停轮, 不再 setState) ──
  const pollExecution = async (fid: string, eid: string) => {
    for (let i = 0; i < 30; i++) {
      if (!mountedRef.current) return
      try {
        const resp = await flowApi.getExecution(fid, eid)
        if (!mountedRef.current) return
        setExecution(resp.data)
        updateNodeStates(resp.data.node_states || {})
        if (["success", "failed", "cancelled"].includes(resp.data.status)) break
      } catch {
        break
      }
      await new Promise((r) => setTimeout(r, 1000))
    }
    if (mountedRef.current) setExecuting(false)
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
        <Button variant="outline" onClick={() => navigate("/flows")}>
          <ArrowLeft className="h-4 w-4" />
          返回工作流
        </Button>
        <Button variant="ghost" onClick={() => navigate("/")}>
          <Home className="h-4 w-4" />
          首页
        </Button>
        <p className="text-sm text-muted-foreground">工作流不存在</p>
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col">
      {/* 顶部工具栏 */}
      <div className="flex items-center gap-3 overflow-x-auto border-b px-4 py-2">
        <Button
          className="shrink-0"
          variant="outline"
          size="sm"
          onClick={() => navigate("/flows")}
          title="返回工作流列表"
        >
          <ArrowLeft className="h-4 w-4" />
          返回工作流
        </Button>
        <Button
          className="shrink-0"
          variant="ghost"
          size="sm"
          onClick={() => navigate("/")}
          title="返回平台首页"
        >
          <Home className="h-4 w-4" />
          首页
        </Button>
        <div className="min-w-40 flex-1">
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
        <Button variant="outline" size="sm" onClick={handleExport} disabled={executing} title="导出画布 JSON">
          <Download className="h-4 w-4" />
          导出
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
          disabled={executing || saving}
          title="导入画布 JSON"
        >
          <Upload className="h-4 w-4" />
          导入
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={handleImportFile}
        />
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
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <NodeToolbox onAdd={handleAddNode} width={toolboxWidth} />
        <PanelResizeHandle
          label="调整元素栏宽度"
          value={toolboxWidth}
          min={140}
          max={320}
          direction={1}
          onPointerDown={(event) => startPanelResize("toolbox", event)}
          onNudge={(delta) => nudgePanel("toolbox", delta)}
        />

        {/* XYFlow 画布 */}
        <div
          ref={canvasRef}
          className="relative min-w-0 flex-1"
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onConnectStart={onConnectStart}
            onConnectEnd={onConnectEnd}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes as unknown as NodeTypes}
            edgeTypes={edgeTypes}
            defaultEdgeOptions={{ type: "deletable" }}
            deleteKeyCode={["Backspace", "Delete"]}
            fitView
            className="bg-secondary/10"
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
            <Controls />
            <MiniMap
              className="!rounded-lg !border"
              nodeColor={(n) => {
                const state = (n.data as { nodeState?: { status?: string } })?.nodeState?.status
                if (state === "success") return "#22c55e"
                if (state === "running") return "#3b82f6"
                if (state === "failed") return "#ef4444"
                if (state === "skipped") return "#9ca3af"
                return "#d1d5db"
              }}
            />
          </ReactFlow>

          {/* 拖线松开弹出的节点选择菜单 */}
          {addMenu.open && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => {
                  setAddMenu({ open: false, x: 0, y: 0 })
                  connectingNodeId.current = null
                  connectingHandleId.current = null
                }}
              />
              <div
                className="fixed z-50 w-44 rounded-lg border bg-popover p-1 shadow-lg"
                style={{
                  left: Math.max(8, Math.min(addMenu.x, window.innerWidth - 184)),
                  top: Math.max(8, Math.min(addMenu.y, window.innerHeight - 332)),
                }}
              >
                <p className="px-2 py-1 text-[11px] text-muted-foreground">添加并连接节点</p>
                {ADDABLE_TYPES.map((item) => (
                  <button
                    key={item.type}
                    onClick={() => handleAddNodeFromMenu(item.type)}
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
                  >
                    <item.icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                    {item.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* 右侧配置面板 */}
        <PanelResizeHandle
          label="调整属性栏宽度"
          value={configWidth}
          min={260}
          max={520}
          direction={-1}
          onPointerDown={(event) => startPanelResize("config", event)}
          onNudge={(delta) => nudgePanel("config", delta)}
        />
        <div className="shrink-0 overflow-hidden border-l bg-background" style={{ width: configWidth }}>
          <NodeConfigPanel
            node={selectedNode}
            allNodes={nodes}
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
