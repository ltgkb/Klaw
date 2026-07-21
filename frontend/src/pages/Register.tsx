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
      navigate("/")
    } catch {
      setError("注册失败，该邮箱可能已注册")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-secondary/30">
      <Card className="w-[400px]">
        <CardHeader>
          <CardTitle className="text-2xl">注册</CardTitle>
          <CardDescription>创建 Claw-Native Agent 平台账号</CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
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
          <CardFooter className="flex flex-col gap-3">
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "注册中..." : "注册"}
            </Button>
            <p className="text-sm text-muted-foreground">
              已有账号？{" "}
              <Link to="/login" className="text-primary underline">
                登录
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </div>
  )
}
