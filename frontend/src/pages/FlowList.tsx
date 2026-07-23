import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Plus, Trash2, Workflow, Loader2, Pencil, X } from "lucide-react"
import { flowApi, type FlowRead } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function FlowList() {
  const navigate = useNavigate()
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

  const fetchFlows = async () => {
    setLoading(true)
    try {
      const resp = await flowApi.list()
      setFlows(resp.data.items)
    } catch {
      // 错误由拦截器处理
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchFlows()
  }, [])

  const handleCreate = async () => {
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
    if (!confirm("确认删除此工作流？所有执行记录将一并删除。")) return
    try {
      await flowApi.delete(flowId)
      await fetchFlows()
    } catch {
      // 错误由拦截器处理
    }
  }

  const beginEdit = (flow: FlowRead) => {
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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Agent 画布</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            XYFlow 拖拽编排 · DAG 执行引擎 · SSE 实时状态
          </p>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)}>
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
            <div className="flex items-center justify-between">
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
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : flows.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <Workflow className="h-12 w-12 text-muted-foreground" />
            <p className="mt-4 text-sm text-muted-foreground">还没有工作流，点击「新建工作流」开始编排</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {flows.map((flow) => (
            <Card
              key={flow.id}
              className="cursor-pointer transition-shadow hover:shadow-md"
              onClick={() => navigate(`/flows/${flow.id}`)}
            >
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <Workflow className="h-5 w-5 text-muted-foreground" />
                    <CardTitle className="text-base">{flow.name}</CardTitle>
                  </div>
                  <div className="flex items-center">
                    <Button
                      variant="ghost"
                      size="icon"
                      title="编辑工作流"
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
                      title="删除工作流"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDelete(flow.id)
                      }}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
                <CardDescription>{flow.description || "无描述"}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                  <span>{flow.dag.nodes?.length ?? 0} 节点</span>
                  <span className="rounded bg-secondary px-1.5 py-0.5">{flow.status}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
