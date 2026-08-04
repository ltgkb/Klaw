import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Plus, Trash2, Workflow, Loader2, Pencil, X } from "lucide-react"
import { flowApi, publicCatalogApi, type FlowRead } from "@/lib/api"
import { useAuthStore } from "@/store/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function FlowList() {
  const navigate = useNavigate()
  const { isAuthenticated } = useAuthStore()
  const [flows, setFlows] = useState<FlowRead[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [creating, setCreating] = useState(false)
  const [editingFlow, setEditingFlow] = useState<FlowRead | null>(null)
  const [editName, setEditName] = useState("")
  const [editDescription, setEditDescription] = useState("")
  const [savingEdit, setSavingEdit] = useState(false)
  const statusLabel = (status: string) => status === "active" ? "已启用" : status === "draft" ? "草稿" : status

  const fetchFlows = async () => {
    setLoading(true)
    try {
      if (isAuthenticated) {
        const resp = await flowApi.list()
        setFlows(resp.data.items)
      } else {
        const resp = await publicCatalogApi.get()
        setFlows(resp.data.flows.map((flow) => ({
          ...flow,
          owner_id: "",
          dag: { nodes: Array.from({ length: flow.node_count }, (_, index) => ({
            id: `public-${index}`,
            type: "text" as const,
            position: { x: 0, y: 0 },
            data: { label: "", config: {} },
          })), edges: [] },
          trigger_type: "manual",
          trigger_config: null,
          created_at: "",
          updated_at: "",
        } as FlowRead)))
      }
    } catch {
      // 错误由拦截器处理
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchFlows()
  }, [isAuthenticated])

  const requireAuth = (next = "/flows") => {
    if (isAuthenticated) return true
    navigate(`/login?next=${encodeURIComponent(next)}`)
    return false
  }

  const handleCreate = async () => {
    if (!requireAuth()) return
    if (!name.trim()) return
    setCreating(true)
    try {
      const resp = await flowApi.create({ name, description: description || undefined })
      setName("")
      setDescription("")
      setShowCreate(false)
      // 创建后直接跳转到画布编辑器
      navigate(`/flows/${resp.data.id}`)
    } catch {
      // 错误由拦截器处理
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (flowId: string) => {
    if (!requireAuth()) return
    if (!confirm("确认删除此工作流？所有执行记录将一并删除。")) return
    try {
      await flowApi.delete(flowId)
      await fetchFlows()
    } catch {
      // 错误由拦截器处理
    }
  }

  const beginEdit = (flow: FlowRead) => {
    if (!requireAuth()) return
    setEditingFlow(flow)
    setEditName(flow.name)
    setEditDescription(flow.description || "")
    setShowCreate(false)
  }

  const handleEdit = async () => {
    if (!editingFlow || !editName.trim()) return
    setSavingEdit(true)
    try {
      await flowApi.update(editingFlow.id, {
        name: editName.trim(),
        description: editDescription,
      })
      setEditingFlow(null)
      await fetchFlows()
    } finally {
      setSavingEdit(false)
    }
  }

  return (
    <div className="kai-flow-page space-y-6">
      <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Agent 画布</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            XYFlow 拖拽编排，支持 DAG 执行与 SSE 实时状态
          </p>
        </div>
        <Button className="w-full sm:w-auto" onClick={() => {
          if (!requireAuth()) return
          setShowCreate(!showCreate)
        }}>
          <Plus className="h-4 w-4" />
          新建工作流
        </Button>
      </div>

      {showCreate && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">创建工作流</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="flow-name">名称</Label>
              <Input
                id="flow-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="我的 Agent 工作流"
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="flow-desc">描述 (可选)</Label>
              <Input
                id="flow-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="工作流用途说明"
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={handleCreate} disabled={creating || !name.trim()}>
                {creating && <Loader2 className="h-4 w-4 animate-spin" />}
                创建
              </Button>
              <Button variant="outline" onClick={() => setShowCreate(false)}>
                取消
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {editingFlow && (
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <CardTitle className="text-base">编辑工作流</CardTitle>
              <Button variant="ghost" size="icon" onClick={() => setEditingFlow(null)} title="取消编辑">
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit-flow-name">名称</Label>
              <Input id="edit-flow-name" value={editName} onChange={(e) => setEditName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-flow-desc">描述</Label>
              <Input id="edit-flow-desc" value={editDescription} onChange={(e) => setEditDescription(e.target.value)} />
            </div>
            <Button onClick={handleEdit} disabled={savingEdit || !editName.trim()}>
              {savingEdit && <Loader2 className="h-4 w-4 animate-spin" />}
              保存修改
            </Button>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2" aria-label="正在加载工作流">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="kai-kb-skeleton h-52 animate-pulse rounded-xl border" />
          ))}
        </div>
      ) : flows.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <Workflow className="h-12 w-12 text-muted-foreground" />
            <p className="mt-4 text-sm text-muted-foreground">还没有工作流，点击「新建工作流」开始编排</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {flows.map((flow) => (
            <Card
              key={flow.id}
              className="group relative overflow-hidden transition-[border-color,box-shadow,transform] duration-200 hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-lg hover:shadow-primary/5"
            >
              <button
                type="button"
                aria-label={`打开 ${flow.name}`}
                className="absolute inset-0 z-0 cursor-pointer rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                onClick={() => {
                  if (!requireAuth(`/flows/${flow.id}`)) return
                  navigate(`/flows/${flow.id}`)
                }}
              />
              <CardHeader className="pointer-events-none relative z-[1] min-h-40 p-5">
                <div className="flex min-w-0 items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
                      <Workflow className="h-4 w-4" />
                    </span>
                    <CardTitle className="line-clamp-2 pt-1.5 text-base leading-5">{flow.name}</CardTitle>
                  </div>
                  {isAuthenticated && <div className="pointer-events-auto relative z-[2] flex shrink-0 items-center">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-foreground"
                      title="编辑工作流"
                      aria-label={`编辑 ${flow.name}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        beginEdit(flow)
                      }}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                      title="删除工作流"
                      aria-label={`删除 ${flow.name}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDelete(flow.id)
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>}
                </div>
                <CardDescription className="line-clamp-3 pl-12 leading-5">{flow.description || "暂无描述"}</CardDescription>
              </CardHeader>
              <CardContent className="pointer-events-none relative z-[1] border-t bg-muted/25 px-5 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span><strong className="font-semibold text-foreground">{flow.dag.nodes?.length ?? 0}</strong> 节点</span>
                  <span className="font-medium text-foreground/75">{statusLabel(flow.status)}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
