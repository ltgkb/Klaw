import { useEffect, useState } from "react"
import { Brain, Bell, Database, Workflow, FileText } from "lucide-react"
import { Link } from "react-router-dom"
import { useAuthStore } from "@/store/auth"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { kbApi, flowApi, memoryApi } from "@/lib/api"

type Stats = {
  kb: number
  flows: number
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
        const [kb, flows, memories] = await Promise.all([
          kbApi.list(1, 1),
          flowApi.list(1, 1),
          memoryApi.list(),
        ])
        setStats({
          kb: kb.data.total,
          flows: flows.data.total,
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
    { icon: Brain, label: "记忆条目", value: stats?.memories, to: "/memories" },
  ]

  const modules = [
    {
      icon: Workflow,
      title: "OpenClaw / Hermes",
      description: "本地 Skills 调用、数据不出域、统一 chat API 与工具发现",
    },
    {
      icon: Bell,
      title: "多平台推送",
      description: "飞书、企微与 Telegram Webhook，支持渠道配置和 notify 节点",
    },
    {
      icon: FileText,
      title: "文件工作区 + 记忆",
      description: "MinIO 文件存储、预签名分享、持久记忆与 Cross-Encoder 精排",
    },
  ]

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">工作台</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {user?.name ? `欢迎回来，${user.name}` : "KAI知识管理与 Agent 工作流概览"}
        </p>
      </div>

      {/* 实时统计 */}
      <Card className="overflow-hidden">
        <CardContent className="grid grid-cols-1 p-0 sm:grid-cols-3">
          {cards.map((c, index) => (
            <Link
              key={c.label}
              to={c.to}
              className={`group flex min-h-28 items-center justify-between px-5 py-5 transition-colors hover:bg-accent/55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${index > 0 ? "border-t sm:border-l sm:border-t-0" : ""}`}
            >
              <div>
                {loading ? (
                  <div className="h-8 w-12 animate-pulse rounded-md bg-muted" aria-label={`正在加载${c.label}`} />
                ) : (
                  <div className="text-3xl font-semibold tracking-tight">{c.value ?? 0}</div>
                )}
                <div className="mt-1.5 text-xs text-muted-foreground">{c.label}</div>
              </div>
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-primary transition-transform group-hover:-translate-y-0.5">
                <c.icon className="h-5 w-5" />
              </span>
            </Link>
          ))}
        </CardContent>
      </Card>

      {/* 模块预览 */}
      <section>
        <h2 className="mb-4 text-base font-semibold">平台能力</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {modules.map((m) => (
            <Card key={m.title} className="bg-card/75">
              <CardHeader className="p-5">
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
                    <m.icon className="h-4 w-4" />
                  </span>
                  <CardTitle className="text-base">{m.title}</CardTitle>
                </div>
                <CardDescription className="mt-3 leading-5">{m.description}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      </section>
    </div>
  )
}
