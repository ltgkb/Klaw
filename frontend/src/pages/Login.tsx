import { useState, type FormEvent } from "react"
import { useNavigate, Link, useSearchParams } from "react-router-dom"
import { useAuthStore } from "@/store/auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"

export function Login() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { login } = useAuthStore()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      await login(email, password)
      const next = searchParams.get("next")
      navigate(next?.startsWith("/") && !next.startsWith("//") ? next : "/kb")
    } catch (err) {
      // 区分错误类型 (P2-12): 凭据错误 / 账号禁用 / 网络故障
      const status = (err as { response?: { status?: number } }).response?.status
      if (status === 401) {
        setError("邮箱或密码错误")
      } else if (status === 403) {
        setError("账号已被禁用，请联系管理员")
      } else if (!status) {
        setError("无法连接服务器，请检查网络后重试")
      } else {
        setError("登录失败，请稍后重试")
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-[100dvh] flex-col bg-background p-4 sm:p-6">
      <Link to="/" className="w-fit text-sm font-semibold tracking-[-0.02em]">KAI知识</Link>
      <main className="flex flex-1 items-center justify-center py-8">
      <Card className="w-full max-w-[420px] shadow-xl shadow-primary/5">
        <CardHeader className="space-y-2 p-6 sm:p-8 sm:pb-6">
          <CardTitle className="text-2xl tracking-tight">登录</CardTitle>
          <CardDescription>进入知识库和 Agent 工作台</CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-5 px-6 sm:px-8">
            {error && (
              <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="email">邮箱</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">密码</Label>
              <Input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
              />
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-4 px-6 pb-6 pt-6 sm:px-8 sm:pb-8">
            <Button type="submit" className="h-10 w-full" disabled={loading}>
              {loading ? "登录中..." : "登录"}
            </Button>
            <p className="text-sm text-muted-foreground">
              还没有账号？{" "}
              <Link to="/register" className="font-medium text-primary underline underline-offset-4">
                注册
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
      </main>
    </div>
  )
}
