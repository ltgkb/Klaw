import { NavLink, useNavigate } from "react-router-dom"
import { LayoutDashboard, BookOpen, Workflow, Settings, LogOut } from "lucide-react"
import { useAuthStore } from "@/store/auth"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const navItems = [
  { to: "/", label: "仪表盘", icon: LayoutDashboard },
  { to: "/kb", label: "知识库", icon: BookOpen, disabled: true },
  { to: "/flows", label: "Agent 画布", icon: Workflow, disabled: true },
  { to: "/settings", label: "系统配置", icon: Settings, disabled: true },
]

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate("/login")
  }

  return (
    <div className="flex h-screen">
      {/* 侧边栏 */}
      <aside className="flex w-60 flex-col border-r bg-secondary/30">
        <div className="flex h-14 items-center border-b px-4 font-semibold">
          🐾 Claw-Native Agent
        </div>
        <nav className="flex-1 space-y-1 p-2">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.disabled ? "#" : item.to}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                item.disabled && "cursor-not-allowed opacity-40",
                !item.disabled && "hover:bg-accent",
              )}
              onClick={(e) => item.disabled && e.preventDefault()}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
              {item.disabled && (
                <span className="ml-auto text-xs text-muted-foreground">M2+</span>
              )}
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* 主区域 */}
      <div className="flex flex-1 flex-col">
        {/* 顶栏 */}
        <header className="flex h-14 items-center justify-between border-b px-6">
          <div className="text-sm text-muted-foreground">
            Claw-Native Agent 平台
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm">
              {user?.name}{" "}
              <span className="rounded bg-secondary px-1.5 py-0.5 text-xs text-secondary-foreground">
                {user?.role}
              </span>
            </span>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="h-4 w-4" />
              退出
            </Button>
          </div>
        </header>

        {/* 内容区 */}
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  )
}
