import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Plus, Trash2, BookOpen, Loader2 } from "lucide-react"
import { kbApi, type KBRead } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function KnowledgeBase() {
  const navigate = useNavigate()
  const [kbs, setKbs] = useState<KBRead[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [chunkStrategy, setChunkStrategy] = useState<"semantic" | "recursive" | "fixed" | "markdown">("recursive")
  const [chunkSize, setChunkSize] = useState(256)
  const [chunkOverlap, setChunkOverlap] = useState(32)
  const [creating, setCreating] = useState(false)

  const fetchKbs = async () => {
    setLoading(true)
    try {
      const resp = await kbApi.list()
      setKbs(resp.data.items)
    } catch {
      // 错误由拦截器处理
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchKbs()
  }, [])

  const handleCreate = async () => {
    if (!name.trim()) return
    setCreating(true)
    try {
      await kbApi.create({
        name,
        description: description || undefined,
        chunk_strategy: chunkStrategy,
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
      })
      setName("")
      setDescription("")
      setChunkStrategy("recursive")
      setChunkSize(256)
      setChunkOverlap(32)
      setShowCreate(false)
      await fetchKbs()
    } catch {
      // 错误由拦截器处理
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (kbId: string) => {
    if (!confirm("确认删除此知识库？所有文档和索引将一并删除。")) return
    try {
      await kbApi.delete(kbId)
      await fetchKbs()
    } catch {
      // 错误由拦截器处理
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">知识库</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            DeepDoc 解析 · BGE-M3 向量化 · ES 混合检索
          </p>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)}>
          <Plus className="h-4 w-4" />
          新建知识库
        </Button>
      </div>

      {showCreate && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">创建知识库</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="kb-name">名称</Label>
              <Input
                id="kb-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="我的知识库"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="kb-desc">描述 (可选)</Label>
              <Input
                id="kb-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="知识库用途说明"
              />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="kb-strategy">分块策略</Label>
                <select
                  id="kb-strategy"
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                  value={chunkStrategy}
                  onChange={(e) => setChunkStrategy(e.target.value as typeof chunkStrategy)}
                >
                  <option value="recursive">递归</option>
                  <option value="fixed">固定长度</option>
                  <option value="markdown">Markdown</option>
                  <option value="semantic">语义</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="kb-size">分块大小 (token)</Label>
                <Input
                  id="kb-size"
                  type="number"
                  value={chunkSize}
                  onChange={(e) => setChunkSize(Number(e.target.value))}
                  min={32}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="kb-overlap">重叠 (token)</Label>
                <Input
                  id="kb-overlap"
                  type="number"
                  value={chunkOverlap}
                  onChange={(e) => setChunkOverlap(Number(e.target.value))}
                  min={0}
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleCreate} disabled={creating || !name.trim()}>
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

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : kbs.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <BookOpen className="h-12 w-12 text-muted-foreground" />
            <p className="mt-4 text-sm text-muted-foreground">还没有知识库，点击「新建知识库」开始</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {kbs.map((kb) => (
            <Card
              key={kb.id}
              className="cursor-pointer transition-shadow hover:shadow-md"
              onClick={() => navigate(`/kb/${kb.id}`)}
            >
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <BookOpen className="h-5 w-5 text-muted-foreground" />
                    <CardTitle className="text-base">{kb.name}</CardTitle>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDelete(kb.id)
                    }}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
                <CardDescription>{kb.description || "无描述"}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                  <span>{kb.document_count} 文档</span>
                  <span>{kb.embedding_model}</span>
                  <span>{kb.chunk_strategy}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
