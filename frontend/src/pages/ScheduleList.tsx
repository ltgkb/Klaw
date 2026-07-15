import { useEffect, useState } from "react"
import { scheduleApi, flowApi, type ScheduleRead, type FlowRead, type ScheduleStatus } from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Plus, Trash2, Clock, Loader2, Pause, Play } from "lucide-react"

export function ScheduleList() {
  const [schedules, setSchedules] = useState<ScheduleRead[]>([])
  const [flows, setFlows] = useState<FlowRead[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [flowId, setFlowId] = useState("")
  const [name, setName] = useState("")
  const [cron, setCron] = useState("")
  const [creating, setCreating] = useState(false)

  const fetchSchedules = async () => {
    setLoading(true)
    try {
      const resp = await scheduleApi.list()
      setSchedules(resp.data)
    } catch {
      // 错误由拦截器处理
    } finally {
      setLoading(false)
    }
  }

  const fetchFlows = async () => {
    try {
      const resp = await flowApi.list()
      setFlows(resp.data.items)
    } catch {
      // 错误由拦截器处理
    }
  }

  useEffect(() => {
    fetchSchedules()
    fetchFlows()
  }, [])

  const handleCreate = async () => {
    if (!flowId || !name.trim() || !cron.trim()) return
    setCreating(true)
    try {
      await scheduleApi.create({ flow_id: flowId, name, cron })
      setFlowId("")
      setName("")
      setCron("")
      setShowCreate(false)
      await fetchSchedules()
    } catch {
      // 错误由拦截器处理
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm("确认删除此定时任务？")) return
    try {
      await scheduleApi.delete(id)
      await fetchSchedules()
    } catch {
      // 错误由拦截器处理
    }
  }

  const handleToggle = async (id: string, current: ScheduleStatus) => {
    const next: ScheduleStatus = current === "active" ? "paused" : "active"
    try {
      await scheduleApi.update(id, { status: next })
      await fetchSchedules()
    } catch {
      // 错误由拦截器处理
    }
  }

  const flowName = (fid: string) =>
    flows.find((f) => f.id === fid)?.name ?? "未知工作流"

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">定时任务</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Cron 调度 · APScheduler 引擎 · 自动触发 Agent 工作流
          </p>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)}>
          <Plus className="h-4 w-4" />
          新建定时任务
        </Button>
      </div>

      {showCreate && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">创建定时任务</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="schedule-flow">关联工作流</Label>
              <select
                id="schedule-flow"
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                value={flowId}
                onChange={(e) => setFlowId(e.target.value)}
              >
                <option value="">选择工作流...</option>
                {flows.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="schedule-name">名称</Label>
              <Input
                id="schedule-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="每日早报推送"
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="schedule-cron">Cron 表达式</Label>
              <Input
                id="schedule-cron"
                value={cron}
                onChange={(e) => setCron(e.target.value)}
                placeholder="0 9 * * *"
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              />
              <p className="text-xs text-muted-foreground">
                分钟 时 日 月 周 (如: 0 9 * * * = 每天9点)
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                onClick={handleCreate}
                disabled={creating || !flowId || !name.trim() || !cron.trim()}
              >
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

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : schedules.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <Clock className="h-12 w-12 text-muted-foreground" />
            <p className="mt-4 text-sm text-muted-foreground">
              还没有定时任务，点击「新建定时任务」开始配置
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {schedules.map((schedule) => (
            <Card key={schedule.id}>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <Clock className="h-5 w-5 text-muted-foreground" />
                    <CardTitle className="text-base">{schedule.name}</CardTitle>
                  </div>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleToggle(schedule.id, schedule.status)}
                    >
                      {schedule.status === "active" ? (
                        <Pause className="h-4 w-4" />
                      ) : (
                        <Play className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(schedule.id)}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
                <CardDescription className="font-mono">{schedule.cron}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                  <span className="truncate">{flowName(schedule.flow_id)}</span>
                  <span>
                    下次:{" "}
                    {schedule.next_run_time
                      ? new Date(schedule.next_run_time).toLocaleString()
                      : "—"}
                  </span>
                  <span
                    className={
                      schedule.status === "active"
                        ? "rounded bg-green-500/15 px-1.5 py-0.5 text-xs text-green-600"
                        : "rounded bg-secondary px-1.5 py-0.5 text-xs"
                    }
                  >
                    {schedule.status}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
