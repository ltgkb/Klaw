import { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import {
  ArrowLeft,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  PlayCircle,
  Pause,
  Play,
  Ban,
} from "lucide-react"
import { flowApi, type ExecutionRead } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

const STATUS_ICON = {
  pending: { icon: Clock, color: "text-muted-foreground", label: "等待中" },
  running: { icon: PlayCircle, color: "text-blue-500", label: "执行中" },
  paused: { icon: Pause, color: "text-amber-500", label: "已暂停" },
  success: { icon: CheckCircle2, color: "text-green-500", label: "成功" },
  failed: { icon: XCircle, color: "text-red-500", label: "失败" },
  cancelled: { icon: XCircle, color: "text-muted-foreground", label: "已取消" },
}

export function ExecutionList() {
  const { flowId } = useParams<{ flowId: string }>()
  const navigate = useNavigate()
  const [executions, setExecutions] = useState<ExecutionRead[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetch = async () => {
      if (!flowId) return
      setLoading(true)
      try {
        const resp = await flowApi.listExecutions(flowId)
        setExecutions(resp.data)
      } catch {
        // 错误由拦截器处理
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [flowId])

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => navigate(`/flows/${flowId}`)}>
          <ArrowLeft className="h-4 w-4" />
          返回画布
        </Button>
        <h1 className="text-2xl font-semibold">执行历史</h1>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : executions.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <Clock className="h-12 w-12 text-muted-foreground" />
            <p className="mt-4 text-sm text-muted-foreground">还没有执行记录</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {executions.map((exec) => {
            const status = STATUS_ICON[exec.status] ?? STATUS_ICON.pending
            const StatusIcon = status.icon
            const nodeCount = Object.keys(exec.node_states || {}).length
            return (
              <Card
                key={exec.id}
                className="cursor-pointer transition-shadow hover:shadow-md"
                onClick={() => navigate(`/flows/${flowId}/executions/${exec.id}`)}
              >
                <CardContent className="flex items-center gap-4 py-4">
                  <StatusIcon className={cn("h-5 w-5", status.color, exec.status === "running" && "animate-pulse")} />
                  <div className="flex-1">
                    <p className="text-sm font-medium">
                      {new Date(exec.created_at).toLocaleString("zh-CN")}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {status.label} · {nodeCount} 节点
                      {exec.error_message && ` · ${exec.error_message}`}
                    </p>
                  </div>
                  <code className="text-xs text-muted-foreground">{exec.id.slice(0, 8)}</code>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function ExecutionDetail() {
  const { flowId, execId } = useParams<{ flowId: string; execId: string }>()
  const navigate = useNavigate()
  const [execution, setExecution] = useState<ExecutionRead | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)

  useEffect(() => {
    const fetch = async () => {
      if (!flowId || !execId) return
      setLoading(true)
      try {
        const resp = await flowApi.getExecution(flowId, execId)
        setExecution(resp.data)
      } catch {
        // 错误由拦截器处理
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [flowId, execId])

  const handleAction = async (action: "pause" | "resume" | "cancel") => {
    if (!flowId || !execId) return
    setActionLoading(true)
    try {
      const resp = await flowApi[`${action}Execution`](flowId, execId)
      setExecution(resp.data)
    } catch {
      // 错误由拦截器处理
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!execution) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate(`/flows/${flowId}/executions`)}>
          <ArrowLeft className="h-4 w-4" />
          返回
        </Button>
        <p className="text-sm text-muted-foreground">执行记录不存在</p>
      </div>
    )
  }

  const status = STATUS_ICON[execution.status] ?? STATUS_ICON.pending
  const nodeStates = execution.node_states || {}

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => navigate(`/flows/${flowId}/executions`)}>
          <ArrowLeft className="h-4 w-4" />
          返回列表
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-semibold">执行详情</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {new Date(execution.created_at).toLocaleString("zh-CN")} ·{" "}
            <span className={status.color}>{status.label}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* 执行控制按钮 (M4) */}
          {execution.status === "running" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleAction("pause")}
              disabled={actionLoading}
            >
              {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Pause className="h-4 w-4" />}
              暂停
            </Button>
          )}
          {execution.status === "paused" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleAction("resume")}
              disabled={actionLoading}
            >
              {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              恢复
            </Button>
          )}
          {(execution.status === "running" || execution.status === "paused") && (
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:bg-destructive/5"
              onClick={() => handleAction("cancel")}
              disabled={actionLoading}
            >
              <Ban className="h-4 w-4" />
              取消
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => navigate(`/flows/${flowId}`)}>
            回到画布
          </Button>
        </div>
      </div>

      {/* 错误信息 */}
      {execution.error_message && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-destructive">错误信息</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap text-sm text-destructive">
              {execution.error_message}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* 输入 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">执行输入</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="whitespace-pre-wrap rounded-md bg-secondary/30 p-3 text-sm">
            {JSON.stringify(execution.input || {}, null, 2)}
          </pre>
        </CardContent>
      </Card>

      {/* 节点执行时间线 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">节点执行时间线 ({Object.keys(nodeStates).length})</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {Object.entries(nodeStates).map(([nodeId, state]) => {
              const nodeStatus = STATUS_ICON[state.status === "running" ? "running" : state.status === "success" ? "success" : "failed"]
              const NodeIcon = nodeStatus.icon
              return (
                <div key={nodeId} className="rounded-md border p-4">
                  <div className="flex items-center gap-2">
                    <NodeIcon className={cn("h-4 w-4", nodeStatus.color)} />
                    <span className="font-medium text-sm">
                      {state.label || nodeId}
                    </span>
                    <code className="text-xs text-muted-foreground">{nodeId.slice(0, 12)}</code>
                    {state.type && (
                      <span className="rounded bg-secondary px-1.5 py-0.5 text-xs text-muted-foreground">
                        {state.type}
                      </span>
                    )}
                    {state.started_at && (
                      <span className="ml-auto text-xs text-muted-foreground">
                        {new Date(state.started_at).toLocaleTimeString("zh-CN")}
                        {state.ended_at && ` → ${new Date(state.ended_at).toLocaleTimeString("zh-CN")}`}
                      </span>
                    )}
                  </div>

                  {state.output && (
                    <div className="mt-2">
                      <p className="text-xs text-muted-foreground mb-1">输出</p>
                      <pre className="whitespace-pre-wrap rounded-md bg-secondary/30 p-2 text-xs">
                        {state.output}
                      </pre>
                    </div>
                  )}

                  {state.error && (
                    <div className="mt-2">
                      <p className="text-xs text-destructive mb-1">错误</p>
                      <pre className="whitespace-pre-wrap rounded-md bg-destructive/5 p-2 text-xs text-destructive">
                        {state.error}
                      </pre>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* 最终输出 */}
      {execution.output && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">最终输出</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap rounded-md bg-secondary/30 p-3 text-sm">
              {JSON.stringify(execution.output, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
