import { Cpu, Clock, Brain, Bell } from "lucide-react"
import { useAuthStore } from "@/store/auth"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const modules = [
  {
    icon: Cpu,
    title: "OpenClaw / Hermes",
    description: "本地 Skills 调用 · 数据不出域 · 统一 chat API",
    status: "已就绪",
  },
  {
    icon: Clock,
    title: "定时任务",
    description: "APScheduler 调度 · PostgreSQL JobStore · Cron 触发",
    status: "已就绪",
  },
  {
    icon: Bell,
    title: "多平台推送",
    description: "飞书 / 企微 / Telegram Webhook · 执行引擎 notify 节点",
    status: "已就绪",
  },
  {
    icon: Brain,
    title: "记忆系统 + 重排序",
    description: "持久记忆读写 · Cross-Encoder 精排 · 人机交互中断",
    status: "已就绪",
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

      {/* 里程碑状态 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">M1 + M2 + M3 + M4 已交付</CardTitle>
          <CardDescription>基础设施 · 用户系统 · 知识库 · 混合检索 · Agent 画布 · 全链路打通</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 text-sm">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            用户系统 (注册/登录/JWT/RBAC) — 已就绪
          </div>
          <div className="mt-2 flex items-center gap-2 text-sm">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            知识库 (DeepDoc/BGE-M3/ES 混合检索/Cross-Encoder 重排序) — 已就绪
          </div>
          <div className="mt-2 flex items-center gap-2 text-sm">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            Agent 画布 (XYFlow/DAG 引擎/SSE 实时状态/暂停恢复) — 已就绪
          </div>
          <div className="mt-2 flex items-center gap-2 text-sm">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            全链路 (模型供应商层/定时调度/推送/记忆/人机交互) — 已就绪
          </div>
        </CardContent>
      </Card>

      {/* 模块预览 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {modules.map((m) => (
          <Card key={m.title}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <m.icon className="h-5 w-5 text-muted-foreground" />
                  <CardTitle className="text-base">{m.title}</CardTitle>
                </div>
                <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700">
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
