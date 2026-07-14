import { Database, Workflow, Cpu, Clock } from "lucide-react"
import { useAuthStore } from "@/store/auth"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const modules = [
  {
    icon: Database,
    title: "知识库",
    description: "DeepDoc 解析 · 向量检索 · 混合检索",
    status: "M2 待开发",
  },
  {
    icon: Workflow,
    title: "Agent 画布",
    description: "XYFlow 拖拽编排 · LangGraph 执行引擎",
    status: "M3 待开发",
  },
  {
    icon: Cpu,
    title: "OpenClaw / Hermes",
    description: "本地 Skills 调用 · 数据不出域",
    status: "M4 待开发",
  },
  {
    icon: Clock,
    title: "定时任务与推送",
    description: "APScheduler 调度 · 飞书/企微/Telegram 推送",
    status: "M4 待开发",
  },
]

export function Dashboard() {
  const { user } = useAuthStore()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">欢迎，{user?.name} 👋</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Claw-Native Agent 平台 — 本地 OpenClaw/Hermes 为一等公民的 Agent 平台
        </p>
      </div>

      {/* M1 基础设施状态 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">M1 基础设施</CardTitle>
          <CardDescription>项目骨架 · 用户系统 · 容器编排</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 text-sm">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            用户系统 (注册/登录/JWT/RBAC) — 已就绪
          </div>
        </CardContent>
      </Card>

      {/* 后续模块预览 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {modules.map((m) => (
          <Card key={m.title}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <m.icon className="h-5 w-5 text-muted-foreground" />
                  <CardTitle className="text-base">{m.title}</CardTitle>
                </div>
                <span className="rounded bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
                  {m.status}
                </span>
              </div>
              <CardDescription className="mt-2">{m.description}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>
    </div>
  )
}
