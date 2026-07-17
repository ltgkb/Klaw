import { useEffect, useState } from "react"
import { Brain, Clock, Bell, Database, Workflow, FileText, Loader2 } from "lucide-react"
import { Link } from "react-router-dom"
import { useAuthStore } from "@/store/auth"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { kbApi, flowApi, scheduleApi, memoryApi } from "@/lib/api"

type Stats = {
  kb: number
  flows: number
  schedules: number
  memories: number
}

export function Dashboard() {
  const { user } = useAuthStore()
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchStats = async () => {
      setLoading(true)
      try {
        const [kb, flows, schedules, memories] = await Promise.all([
          kbApi.list(1, 1),
          flowApi.list(1, 1),
          scheduleApi.list(),
          memoryApi.list(),
        ])
        setStats({
          kb: kb.data.total,
          flows: flows.data.total,
          schedules: schedules.data.length,
          memories: memories.data.length,
        })
      } catch {
        // 错误由拦截器处理
      } finally {
        setLoading(false)
      }
    }
    fetchStats()
  }, [])

  const cards = [
    { icon: Database, label: "知识库", value: stats?.kb, to: "/kb" },
    { icon: Workflow, label: "工作流", value: stats?.flows, to: "/flows" },
    { icon: Clock, label: "定时任务", value: stats?.schedules, to: "/schedules" },
    { icon: Brain, label: "记忆条目", value: stats?.memories, to: "/memories" },
  ]

  const modules = [
    {
      icon: Workflow,
      title: "OpenClaw / Hermes",
      description: "本地 Skills 调用 · 数据不出域 · 统一 chat API · 工具发现",
    },
    {
      icon: Clock,
      title: "定时任务",
      description: "APScheduler 调度 · PostgreSQL JobStore · Cron 触发",
    },
    {
      icon: Bell,
      title: "多平台推送",
      description: "飞书 / 企微 / Telegram Webhook · 渠道配置 · notify 节点",
    },
    {
      icon: FileText,
      title: "文件工作区 + 记忆",
      description: "MinIO 文件存储 · 预签名分享 · 持久记忆 · Cross-Encoder 精排",
    },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">欢迎，{user?.name} 👋</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Claw-Native Agent 平台 — 本地 OpenClaw/Hermes 为一等公民的 Agent 平台
        </p>
      </div>

      {/* 实时统计 */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {cards.map((c) => (
          <Link key={c.label} to={c.to}>
            <Card className="transition-colors hover:bg-muted/40">
              <CardContent className="flex items-center justify-between p-5">
                <div>
                  <div className="text-2xl font-semibold">
                    {loading ? <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /> : c.value ?? 0}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">{c.label}</div>
                </div>
                <c.icon className="h-8 w-8 text-muted-foreground/60" />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {/* 模块预览 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {modules.map((m) => (
          <Card key={m.title}>
            <CardHeader>
              <div className="flex items-center gap-3">
                <m.icon className="h-5 w-5 text-muted-foreground" />
                <CardTitle className="text-base">{m.title}</CardTitle>
              </div>
              <CardDescription className="mt-2">{m.description}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>
    </div>
  )
}

