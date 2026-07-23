import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Plus, Trash2, BookOpen, Loader2, Upload, FolderOpen, X } from "lucide-react"
import { kbApi, type KBRead } from "@/lib/api"
import { toast } from "@/lib/toast"
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
  const [showImport, setShowImport] = useState(false)
  const [importName, setImportName] = useState("")
  const [importFiles, setImportFiles] = useState<File[]>([])
  const [importing, setImporting] = useState(false)
  const importInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const chunkConfigValid =
    chunkSize >= 100 &&
    chunkSize <= 4096 &&
    chunkOverlap >= 0 &&
    chunkOverlap < chunkSize

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

  useEffect(() => {
    folderInputRef.current?.setAttribute("webkitdirectory", "")
    folderInputRef.current?.setAttribute("directory", "")
  }, [showImport])

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

  const selectImportFiles = (files: FileList | null) => {
    if (!files) return
    const supported = Array.from(files).filter((file) =>
      /\.(pdf|docx|xlsx|csv|pptx|txt|md|markdown|html|htm|json|epub)$/i.test(file.name),
    )
    setImportFiles(supported)
    if (!importName && supported.length > 0) {
      const relativeRoot = supported[0].webkitRelativePath?.split("/")[0]
      setImportName(relativeRoot || supported[0].name.replace(/\.[^.]+$/, ""))
    }
    if (supported.length !== files.length) {
      toast.error(`已忽略 ${files.length - supported.length} 个不支持的文件`)
    }
  }

  const resetImport = () => {
    setShowImport(false)
    setImportName("")
    setImportFiles([])
    if (importInputRef.current) importInputRef.current.value = ""
    if (folderInputRef.current) folderInputRef.current.value = ""
  }

  const handleImport = async () => {
    if (!importName.trim() || importFiles.length === 0 || importing) return
    setImporting(true)
    try {
      const created = await kbApi.create({ name: importName.trim() })
      let failed = 0
      for (const file of importFiles) {
        try {
          await kbApi.uploadDocument(created.data.id, file)
        } catch {
          failed += 1
        }
      }
      if (failed > 0) {
        toast.error(`知识库已创建，${importFiles.length - failed} 个文件已导入，${failed} 个失败`)
      } else {
        toast.success(`已导入 ${importFiles.length} 个文件`)
      }
      resetImport()
      navigate(`/kb/${created.data.id}`)
    } finally {
      setImporting(false)
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
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => { setShowImport(!showImport); setShowCreate(false) }}>
            <Upload className="h-4 w-4" />
            导入知识库
          </Button>
          <Button onClick={() => { setShowCreate(!showCreate); setShowImport(false) }}>
            <Plus className="h-4 w-4" />
            新建知识库
          </Button>
        </div>
      </div>

      {showImport && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">导入知识库</CardTitle>
                <CardDescription>选择文件或文件夹，自动创建知识库并开始解析</CardDescription>
              </div>
              <Button variant="ghost" size="icon" onClick={resetImport} title="取消导入">
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="import-kb-name">知识库名称</Label>
              <Input
                id="import-kb-name"
                value={importName}
                onChange={(e) => setImportName(e.target.value)}
                placeholder="导入的知识库"
              />
            </div>
            <input
              ref={importInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.xlsx,.csv,.pptx,.txt,.md,.markdown,.html,.htm,.json,.epub"
              className="hidden"
              onChange={(e) => selectImportFiles(e.target.files)}
            />
            <input
              ref={folderInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => selectImportFiles(e.target.files)}
            />
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => importInputRef.current?.click()} disabled={importing}>
                <Upload className="h-4 w-4" /> 选择文件
              </Button>
              <Button variant="outline" onClick={() => folderInputRef.current?.click()} disabled={importing}>
                <FolderOpen className="h-4 w-4" /> 选择文件夹
              </Button>
              <span className="self-center text-sm text-muted-foreground">
                {importFiles.length > 0 ? `已选择 ${importFiles.length} 个文件` : "尚未选择文件"}
              </span>
            </div>
            <Button onClick={handleImport} disabled={importing || !importName.trim() || importFiles.length === 0}>
              {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              {importing ? "正在导入" : "开始导入"}
            </Button>
          </CardContent>
        </Card>
      )}

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
                  onChange={(e) => {
                    const size = Number(e.target.value)
                    setChunkSize(size)
                    if (Number.isFinite(size) && chunkOverlap >= size) {
                      setChunkOverlap(Math.max(0, size - 1))
                    }
                  }}
                  min={100}
                  max={4096}
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
                  max={Math.max(0, chunkSize - 1)}
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleCreate} disabled={creating || !name.trim() || !chunkConfigValid}>
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
