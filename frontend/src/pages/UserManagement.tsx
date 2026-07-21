import { useEffect, useState } from "react"
import { Loader2, ShieldCheck, Users as UsersIcon } from "lucide-react"
import { usersApi, type UserRead } from "@/lib/api"
import { toast } from "@/lib/toast"
import { useAuthStore } from "@/store/auth"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const ROLE_LABELS: Record<UserRead["role"], string> = {
  admin: "管理员",
  user: "普通用户",
  viewer: "只读用户",
}

export function UserManagement() {
  const { user: currentUser } = useAuthStore()
  const [users, setUsers] = useState<UserRead[]>([])
  const [loading, setLoading] = useState(true)
  const [forbidden, setForbidden] = useState(false)
  const [savingId, setSavingId] = useState<string | null>(null)

  const fetchUsers = async () => {
    setLoading(true)
    try {
      const resp = await usersApi.list()
      setUsers(resp.data)
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status
      if (status === 403) setForbidden(true)
      // 其它错误由拦截器 toast
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchUsers()
  }, [])

  const handleRoleChange = async (id: string, role: UserRead["role"]) => {
    setSavingId(id)
    try {
      await usersApi.updateRole(id, role)
      toast.success("角色已更新")
      await fetchUsers()
    } catch {
      // 错误由拦截器处理 (如最后一个 admin 不可降级)
    } finally {
      setSavingId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (forbidden) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">用户管理</h1>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <ShieldCheck className="h-12 w-12 text-muted-foreground" />
            <p className="mt-4 text-sm text-muted-foreground">
              需要管理员权限才能访问用户管理
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">用户管理</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          平台账号列表 · 角色调整 (仅管理员)
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <UsersIcon className="h-5 w-5 text-muted-foreground" />
            <div>
              <CardTitle className="text-base">用户列表 ({users.length})</CardTitle>
              <CardDescription>最后一个管理员不可被降级 (后端强制)</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {users.map((u) => (
              <div key={u.id} className="flex items-center gap-3 rounded-md border p-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {u.name}
                    {u.id === currentUser?.id && (
                      <span className="ml-2 rounded bg-secondary px-1.5 py-0.5 text-xs text-muted-foreground">
                        我
                      </span>
                    )}
                    {!u.is_active && (
                      <span className="ml-2 rounded bg-destructive/10 px-1.5 py-0.5 text-xs text-destructive">
                        已禁用
                      </span>
                    )}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">{u.email}</p>
                </div>
                <select
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                  value={u.role}
                  disabled={savingId === u.id}
                  onChange={(e) => handleRoleChange(u.id, e.target.value as UserRead["role"])}
                >
                  {(Object.keys(ROLE_LABELS) as UserRead["role"][]).map((role) => (
                    <option key={role} value={role}>
                      {ROLE_LABELS[role]}
                    </option>
                  ))}
                </select>
                {savingId === u.id && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
