import { useState, type FormEvent } from "react"
import { useNavigate, Link } from "react-router-dom"
import { useAuthStore } from "@/store/auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"

export function Register() {
  const navigate = useNavigate()
  const { register } = useAuthStore()
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [passwordConfirm, setPasswordConfirm] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError("")
    if (password.length < 6) {
      setError("密码至少 6 位")
      return
    }
    if (password !== passwordConfirm) {
      setError("两次输入的密码不一致")
      return
    }
    setLoading(true)
    try {
      await register(email, name, password)
      navigate("/kb")
    } catch {
      setError("注册失败，该邮箱可能已注册")
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
          <CardTitle className="text-2xl tracking-tight">创建账号</CardTitle>
          <CardDescription>注册后进入 KAI知识管理平台</CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-5 px-6 sm:px-8">
            {error && (
              <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="name">用户名</Label>
              <Input
                id="name"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="你的名字"
              />
            </div>
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
                placeholder="至少 6 位"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password-confirm">确认密码</Label>
              <Input
                id="password-confirm"
                type="password"
                required
                value={passwordConfirm}
                onChange={(e) => setPasswordConfirm(e.target.value)}
                placeholder="再次输入密码"
              />
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-4 px-6 pb-6 pt-6 sm:px-8 sm:pb-8">
            <Button type="submit" className="h-10 w-full" disabled={loading}>
              {loading ? "注册中..." : "注册"}
            </Button>
            <p className="text-sm text-muted-foreground">
              已有账号？{" "}
              <Link to="/login" className="font-medium text-primary underline underline-offset-4">
                登录
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
      </main>
    </div>
  )
}
