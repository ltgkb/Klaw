import { Link, NavLink, useLocation, useNavigate } from "react-router-dom"
import { LayoutDashboard, BookOpen, Workflow, Settings, Brain, LogIn, LogOut, Bot, FolderOpen, Users, House } from "lucide-react"
import { useAuthStore } from "@/store/auth"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const navItems = [
  { to: "/kb", label: "知识库", icon: BookOpen },
  { to: "/flows", label: "Agent 画布", icon: Workflow },
  { to: "/agents", label: "对话 Agent", icon: Bot },
  { to: "/dashboard", label: "仪表盘", icon: LayoutDashboard },
  { to: "/memories", label: "记忆系统", icon: Brain },
  { to: "/files", label: "文件", icon: FolderOpen },
  { to: "/users", label: "用户管理", icon: Users, adminOnly: true },
  { to: "/settings", label: "系统配置", icon: Settings },
]

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, logout, isAuthenticated } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const visibleNavItems = navItems.filter(
    (item) =>
      (!("adminOnly" in item) || user?.role === "admin") &&
      (isAuthenticated || item.to === "/kb" || item.to === "/flows"),
  )

  const handleLogout = () => {
    logout()
    navigate("/login")
  }

  return (
    <div className="kai-admin-shell flex h-[100dvh] min-w-0">
      {/* 侧边栏 */}
      <aside className="kai-admin-sidebar hidden w-60 shrink-0 flex-col border-r md:flex">
        <Link
          to="/"
          title="返回问答首屏"
          className="kai-admin-brand flex h-16 items-center gap-2.5 border-b px-4 font-semibold transition-colors hover:bg-accent"
        >
          <House className="h-4 w-4" />
          KAI知识
        </Link>
        <nav className="flex-1 space-y-1.5 p-3">
          {visibleNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg border border-transparent px-3 py-2.5 text-sm font-medium transition-[color,background-color,border-color,transform] active:translate-y-px",
                  isActive ? "border-primary/15 bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/70 hover:text-foreground",
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* 主区域 */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* 顶栏 */}
        <header className="kai-admin-header flex h-16 shrink-0 items-center justify-between gap-2 border-b px-3 sm:px-6">
          <Link
            to="/"
            title="返回问答首屏"
            className="flex min-w-0 items-center gap-2 truncate text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <House className="h-4 w-4 shrink-0" />
            KAI知识
          </Link>
          <div className="flex shrink-0 items-center gap-2 sm:gap-4">
            {isAuthenticated ? (
              <>
                <span className="hidden text-sm sm:inline">
                  {user?.name}{" "}
                  <span className="rounded bg-secondary px-1.5 py-0.5 text-xs text-secondary-foreground">
                    {user?.role}
                  </span>
                </span>
                <Button variant="ghost" size="sm" onClick={handleLogout}>
                  <LogOut className="h-4 w-4" />
                  <span className="hidden sm:inline">退出</span>
                </Button>
              </>
            ) : (
              <Button variant="outline" size="sm" onClick={() => navigate(`/login?next=${encodeURIComponent(location.pathname)}`)}>
                <LogIn className="h-4 w-4" />
                登录
              </Button>
            )}
          </div>
        </header>

        <nav className="kai-mobile-nav flex shrink-0 gap-1 overflow-x-auto border-b px-2 py-2 md:hidden">
          {visibleNavItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => cn(
                  "flex shrink-0 items-center gap-2 rounded-lg border border-transparent px-3 py-2 text-sm",
                  isActive ? "border-primary/15 bg-accent text-accent-foreground" : "text-muted-foreground",
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            ))}
        </nav>

        {/* 内容区 */}
        <main className="min-w-0 flex-1 overflow-auto p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  )
}
