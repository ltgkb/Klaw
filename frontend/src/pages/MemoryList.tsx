import { useEffect, useState } from "react"
import { memoryApi, type MemoryRead, type MemoryType } from "@/lib/api"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Plus, Trash2, Brain, Loader2, Search } from "lucide-react"

const typeBadgeClass: Record<MemoryType, string> = {
  preference: "bg-blue-100 text-blue-700",
  decision: "bg-amber-100 text-amber-700",
  context: "bg-gray-100 text-gray-700",
}

const typeLabel: Record<MemoryType, string> = {
  preference: "偏好",
  decision: "决策",
  context: "上下文",
}

const formatTime = (iso: string): string => new Date(iso).toLocaleString("zh-CN")

export function MemoryList() {
  const [memories, setMemories] = useState<MemoryRead[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)

  // 创建表单
  const [newType, setNewType] = useState<MemoryType>("preference")
  const [newKey, setNewKey] = useState("")
  const [newValue, setNewValue] = useState("")
  const [newSessionId, setNewSessionId] = useState("")

  // 搜索
  const [searchQuery, setSearchQuery] = useState("")
  const [searching, setSearching] = useState(false)
  const [isSearchMode, setIsSearchMode] = useState(false)

  const fetchMemories = async () => {
    setLoading(true)
    setIsSearchMode(false)
    try {
      const resp = await memoryApi.list()
      setMemories(resp.data)
    } catch {
      // 错误由拦截器处理
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchMemories()
  }, [])

  const handleCreate = async () => {
    if (!newKey.trim()) return
    setCreating(true)
    try {
      let parsedValue: Record<string, unknown>
      try {
        const parsed = JSON.parse(newValue)
        if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
          parsedValue = parsed as Record<string, unknown>
        } else {
          parsedValue = { value: newValue }
        }
      } catch {
        parsedValue = { value: newValue }
      }
      await memoryApi.create({
        type: newType,
        key: newKey.trim(),
        value: parsedValue,
        session_id: newSessionId.trim() || undefined,
      })
      setNewType("preference")
      setNewKey("")
      setNewValue("")
      setNewSessionId("")
      setShowCreate(false)
      await fetchMemories()
    } catch {
      // 错误由拦截器处理
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm("确认删除此记忆？")) return
    try {
      await memoryApi.delete(id)
      await fetchMemories()
    } catch {
      // 错误由拦截器处理
    }
  }

  const handleSearch = async () => {
    const q = searchQuery.trim()
    if (!q) {
      await fetchMemories()
      return
    }
    setSearching(true)
    setIsSearchMode(true)
    try {
      const resp = await memoryApi.search(q)
      setMemories(resp.data)
    } catch {
      // 错误由拦截器处理
    } finally {
      setSearching(false)
    }
  }

  const clearSearch = async () => {
    setSearchQuery("")
    await fetchMemories()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">记忆系统</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            持久记忆 · 偏好/决策/上下文
          </p>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)}>
          <Plus className="h-4 w-4" />
          新建记忆
        </Button>
      </div>

      <div className="flex gap-2">
        <Input
          placeholder="搜索记忆..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
        />
        <Button onClick={handleSearch} disabled={searching}>
          {searching ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Search className="h-4 w-4" />
          )}
          搜索
        </Button>
        {isSearchMode && (
          <Button variant="outline" onClick={clearSearch}>
            显示全部
          </Button>
        )}
      </div>

      {showCreate && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">创建记忆</CardTitle>
            <CardDescription>偏好、决策与上下文将持久化保存</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="memory-type">类型</Label>
              <select
                id="memory-type"
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                value={newType}
                onChange={(e) => setNewType(e.target.value as MemoryType)}
              >
                <option value="preference">偏好 (preference)</option>
                <option value="decision">决策 (decision)</option>
                <option value="context">上下文 (context)</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="memory-key">键 (Key)</Label>
              <Input
                id="memory-key"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder="preferred_model"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="memory-value">值 (JSON 或文本)</Label>
              <textarea
                id="memory-value"
                className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder='{"model": "gpt-4"}'
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="memory-session">会话 ID (可选)</Label>
              <Input
                id="memory-session"
                value={newSessionId}
                onChange={(e) => setNewSessionId(e.target.value)}
                placeholder="sess_xxx"
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={handleCreate} disabled={creating || !newKey.trim()}>
                {creating && <Loader2 className="h-4 w-4 animate-spin" />}
                创建
              </Button>
              <Button variant="outline" onClick={() => setShowCreate(false)}>
                取消
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {isSearchMode && (
        <p className="text-sm text-muted-foreground">
          搜索结果 · 关键词「{searchQuery}」· 共 {memories.length} 条
        </p>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : memories.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <Brain className="h-12 w-12 text-muted-foreground" />
            <p className="mt-4 text-sm text-muted-foreground">
              {isSearchMode
                ? "未找到匹配的记忆"
                : "还没有记忆，点击「新建记忆」开始记录"}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {memories.map((memory) => (
            <Card key={memory.id}>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded px-2 py-0.5 text-xs ${typeBadgeClass[memory.type]}`}
                    >
                      {typeLabel[memory.type]}
                    </span>
                    <CardTitle className="text-base">{memory.key}</CardTitle>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(memory.id)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                <pre className="overflow-x-auto rounded-md bg-secondary/30 p-2 text-xs">
                  {JSON.stringify(memory.value, null, 2)}
                </pre>
                <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                  {memory.session_id && <span>会话: {memory.session_id}</span>}
                  <span>{formatTime(memory.updated_at)}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
