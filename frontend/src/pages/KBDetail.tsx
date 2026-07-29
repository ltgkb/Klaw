import { useEffect, useState, useRef } from "react"
import { useParams, useNavigate } from "react-router-dom"
import {
  ArrowLeft,
  Upload,
  Trash2,
  Search,
  Loader2,
  FileText,
  CheckCircle2,
  Clock,
  AlertCircle,
  Pencil,
  RotateCcw,
  Save,
  X,
} from "lucide-react"
import { kbApi, type KBRead, type DocumentRead, type SearchHit, type ChunkRead } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "@/lib/toast"

const STATUS_CONFIG = {
  pending: { icon: Clock, label: "等待中", color: "text-muted-foreground" },
  parsing: { icon: Loader2, label: "解析中", color: "text-blue-500" },
  parsed: { icon: CheckCircle2, label: "已完成", color: "text-green-500" },
  failed: { icon: AlertCircle, label: "失败", color: "text-destructive" },
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function KBDetail() {
  const { kbId } = useParams<{ kbId: string }>()
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [kb, setKb] = useState<KBRead | null>(null)
  const [docs, setDocs] = useState<DocumentRead[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [reparsingId, setReparsingId] = useState<string | null>(null)

  // 检索
  const [query, setQuery] = useState("")
  const [searching, setSearching] = useState(false)
  const [hits, setHits] = useState<SearchHit[]>([])
  const [rerank, setRerank] = useState(false)
  // 只有真正执行过检索才显示「无匹配结果」 (P2-11)
  const [hasSearched, setHasSearched] = useState(false)

  // Chunk 浏览 (分页)
  const [chunks, setChunks] = useState<ChunkRead[]>([])
  const [chunkTotal, setChunkTotal] = useState(0)
  const [chunkPage, setChunkPage] = useState(1)
  const [chunksLoading, setChunksLoading] = useState(false)
  const [editingChunkId, setEditingChunkId] = useState<string | null>(null)
  const [chunkDraft, setChunkDraft] = useState("")
  const [savingChunkId, setSavingChunkId] = useState<string | null>(null)
  const [selectedChunkIds, setSelectedChunkIds] = useState<Set<string>>(new Set())
  const [deletingChunks, setDeletingChunks] = useState(false)
  const CHUNK_PAGE_SIZE = 10

  const fetchAll = async () => {
    if (!kbId) return
    setLoading(true)
    try {
      const [kbResp, docsResp] = await Promise.all([
        kbApi.get(kbId),
        kbApi.listDocuments(kbId),
      ])
      setKb(kbResp.data)
      setDocs(docsResp.data)
    } catch {
      // 错误由拦截器处理
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId])

  // Chunk 分页加载
  const fetchChunks = async (page: number) => {
    if (!kbId) return
    setChunksLoading(true)
    try {
      const resp = await kbApi.listChunks(kbId, page, CHUNK_PAGE_SIZE)
      setChunks(resp.data.items)
      setChunkTotal(resp.data.total)
      setChunkPage(resp.data.page)
      setSelectedChunkIds(new Set())
      cancelEditingChunk()
    } catch {
      // 错误由拦截器处理
    } finally {
      setChunksLoading(false)
    }
  }

  useEffect(() => {
    fetchChunks(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId])

  // 如果有文档正在解析，轮询状态
  useEffect(() => {
    const hasParsing = docs.some((d) => d.parse_status === "pending" || d.parse_status === "parsing")
    if (!hasParsing) return
    const timer = setInterval(fetchAll, 3000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docs])

  const handleUpload = async (files: FileList | null) => {
    if (!kbId || !files || files.length === 0) return
    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        await kbApi.uploadDocument(kbId, file)
      }
      await fetchAll()
    } catch {
      // 错误由拦截器处理
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  const handleDeleteDoc = async (docId: string) => {
    if (!kbId) return
    if (!confirm("确认删除此文档？")) return
    try {
      await kbApi.deleteDocument(kbId, docId)
      await fetchAll()
    } catch {
      // 错误由拦截器处理
    }
  }

  const handleReparseDoc = async (docId: string) => {
    if (!kbId) return
    setReparsingId(docId)
    try {
      await kbApi.reparseDocument(kbId, docId)
      await fetchAll()
    } catch {
      // 错误由拦截器处理
    } finally {
      setReparsingId(null)
    }
  }

  const handleSearch = async () => {
    if (!kbId || !query.trim()) return
    setSearching(true)
    try {
      const resp = await kbApi.search(kbId, { query, top_k: 10, rerank })
      setHits(resp.data.hits)
      setHasSearched(true)
    } catch {
      // 错误由拦截器处理
    } finally {
      setSearching(false)
    }
  }

  const startEditingChunk = (chunk: ChunkRead) => {
    setEditingChunkId(chunk.id)
    setChunkDraft(chunk.content)
  }

  const cancelEditingChunk = () => {
    setEditingChunkId(null)
    setChunkDraft("")
  }

  const saveChunk = async (chunkId: string) => {
    if (!kbId || !chunkDraft.trim()) return
    setSavingChunkId(chunkId)
    try {
      const response = await kbApi.updateChunk(kbId, chunkId, chunkDraft)
      setChunks((current) =>
        current.map((chunk) => chunk.id === chunkId ? response.data : chunk),
      )
      setHits([])
      setHasSearched(false)
      cancelEditingChunk()
      toast.success("Chunk 已保存并重新建立检索索引")
    } catch {
      // 错误由拦截器处理
    } finally {
      setSavingChunkId(null)
    }
  }

  const toggleChunkSelection = (chunkId: string) => {
    setSelectedChunkIds((current) => {
      const next = new Set(current)
      if (next.has(chunkId)) next.delete(chunkId)
      else next.add(chunkId)
      return next
    })
  }

  const toggleCurrentPage = () => {
    const allSelected = chunks.length > 0 && chunks.every((chunk) => selectedChunkIds.has(chunk.id))
    setSelectedChunkIds(allSelected ? new Set() : new Set(chunks.map((chunk) => chunk.id)))
  }

  const deleteSelectedChunks = async (chunkIds: string[]) => {
    if (!kbId || chunkIds.length === 0 || deletingChunks) return
    const label = chunkIds.length === 1 ? "这个 Chunk" : `选中的 ${chunkIds.length} 个 Chunk`
    if (!confirm(`确认删除${label}？删除后无法恢复。`)) return
    setDeletingChunks(true)
    try {
      const response = await kbApi.deleteChunks(kbId, chunkIds)
      const remainingOnPage = chunks.length - response.data.deleted
      const targetPage = remainingOnPage === 0 && chunkPage > 1 ? chunkPage - 1 : chunkPage
      setSelectedChunkIds(new Set())
      if (chunkIds.includes(editingChunkId ?? "")) cancelEditingChunk()
      await fetchChunks(targetPage)
      toast.success(`已删除 ${response.data.deleted} 个 Chunk`)
    } catch {
      // 错误由拦截器处理
    } finally {
      setDeletingChunks(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!kb) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/kb")}>
          <ArrowLeft className="h-4 w-4" />
          返回
        </Button>
        <p className="text-sm text-muted-foreground">知识库不存在</p>
      </div>
    )
  }

  return (
    <div className="kai-kb-page space-y-6">
      {/* 头部 */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => navigate("/kb")}>
          <ArrowLeft className="h-4 w-4" />
          返回
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-semibold">{kb.name}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {kb.description || "无描述"} · {kb.embedding_model} · {kb.chunk_strategy}
          </p>
        </div>
      </div>

      {/* 文档上传 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">文档管理</CardTitle>
          <CardDescription>支持 PDF / DOCX / XLSX / CSV / PPTX / TXT / MD / HTML / JSON / EPUB</CardDescription>
        </CardHeader>
        <CardContent>
          <div
            className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors hover:border-primary"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              handleUpload(e.dataTransfer.files)
            }}
          >
            <Upload className="h-8 w-8 text-muted-foreground" />
            <p className="mt-2 text-sm text-muted-foreground">拖拽文件到此处或点击上传</p>
            <Input
              ref={fileInputRef}
              type="file"
              multiple
              className="mt-2 hidden"
              onChange={(e) => handleUpload(e.target.files)}
            />
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading && <Loader2 className="h-4 w-4 animate-spin" />}
              选择文件
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* 文档列表 */}
      {docs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">文档列表 ({docs.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {docs.map((doc) => {
                const status = STATUS_CONFIG[doc.parse_status]
                const StatusIcon = status.icon
                return (
                  <div
                    key={doc.id}
                    className="flex items-center gap-3 rounded-md border p-3"
                  >
                    <FileText className="h-5 w-5 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{doc.filename}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatSize(doc.file_size)}
                        {doc.page_count > 0 && ` · ${doc.page_count} 页`}
                      </p>
                      {doc.parse_status === "failed" && doc.parse_error && (
                        <p className="mt-1 line-clamp-2 text-xs text-destructive" title={doc.parse_error}>
                          {doc.parse_error}
                        </p>
                      )}
                    </div>
                    <div className={`flex items-center gap-1 text-xs ${status.color}`}>
                      <StatusIcon className={`h-3.5 w-3.5 ${doc.parse_status === "parsing" && "animate-spin"}`} />
                      {status.label}
                    </div>
                    {doc.parse_status === "failed" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleReparseDoc(doc.id)}
                        disabled={reparsingId === doc.id}
                        title="重新解析"
                        aria-label={`重新解析 ${doc.filename}`}
                      >
                        <RotateCcw className={`h-4 w-4 ${reparsingId === doc.id ? "animate-spin" : ""}`} />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDeleteDoc(doc.id)}
                      title="删除文档"
                      aria-label={`删除 ${doc.filename}`}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 检索测试 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">检索测试</CardTitle>
          <CardDescription>混合检索: 向量 (kNN) + 全文 (BM25)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                setHasSearched(false)
              }}
              placeholder="输入检索内容..."
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
            <Button onClick={handleSearch} disabled={searching || !query.trim()}>
              {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              检索
            </Button>
          </div>

          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={rerank}
              onChange={(e) => setRerank(e.target.checked)}
              className="h-4 w-4"
            />
            Cross-Encoder 重排序 (rerank)
          </label>

          {hits.length > 0 && (
            <div className="space-y-3">
              <Label className="text-xs text-muted-foreground">检索结果 ({hits.length})</Label>
              {hits.map((hit, i) => (
                <div key={i} className="rounded-md border p-3">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="rounded bg-secondary px-1.5 py-0.5 text-xs">
                      {hit.content_type}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      score: {hit.score.toFixed(4)}
                      {hit.rerank_score != null && ` · rerank: ${hit.rerank_score.toFixed(4)}`}
                    </span>
                  </div>
                  <p className="text-sm whitespace-pre-wrap">{hit.content}</p>
                </div>
              ))}
            </div>
          )}

          {hasSearched && hits.length === 0 && !searching && (
            <p className="text-sm text-muted-foreground">无匹配结果</p>
          )}
        </CardContent>
      </Card>

      {/* Chunk 浏览 (分页) */}
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle className="text-base">Chunk 浏览</CardTitle>
              <CardDescription>共 {chunkTotal} 个分块 · 每页 {CHUNK_PAGE_SIZE} 条</CardDescription>
            </div>
            {chunks.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" size="sm" onClick={toggleCurrentPage} disabled={deletingChunks}>
                  {chunks.every((chunk) => selectedChunkIds.has(chunk.id)) ? "取消全选" : "全选当前页"}
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => deleteSelectedChunks(Array.from(selectedChunkIds))}
                  disabled={selectedChunkIds.size === 0 || deletingChunks}
                >
                  {deletingChunks
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : <Trash2 className="h-4 w-4" />}
                  删除所选{selectedChunkIds.size > 0 ? ` (${selectedChunkIds.size})` : ""}
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {chunksLoading ? (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : chunks.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">暂无分块，请先上传并解析文档</p>
          ) : (
            <div className="space-y-2">
              {chunks.map((chunk) => (
                <div
                  key={chunk.id}
                  className={`rounded-md border p-3 ${selectedChunkIds.has(chunk.id) ? "border-primary bg-accent/40" : ""}`}
                >
                  <div className="mb-1 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={selectedChunkIds.has(chunk.id)}
                        onChange={() => toggleChunkSelection(chunk.id)}
                        aria-label={`选择第 ${chunk.page} 页 Chunk`}
                        className="h-4 w-4 accent-primary"
                      />
                      <span className="rounded bg-secondary px-1.5 py-0.5 text-xs">
                        {chunk.content_type}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        第 {chunk.page} 页{chunk.embedding_stored ? " · 已向量化" : ""}
                      </span>
                      {editingChunkId !== chunk.id && (
                        <>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => startEditingChunk(chunk)}
                            title="编辑 Chunk"
                            aria-label={`编辑第 ${chunk.page} 页 Chunk`}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => deleteSelectedChunks([chunk.id])}
                            disabled={deletingChunks}
                            title="删除 Chunk"
                            aria-label={`删除第 ${chunk.page} 页 Chunk`}
                          >
                            <Trash2 className="h-3.5 w-3.5 text-destructive" />
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                  {editingChunkId === chunk.id ? (
                    <div className="space-y-2">
                      <Label htmlFor={`chunk-${chunk.id}`} className="sr-only">Chunk 内容</Label>
                      <textarea
                        id={`chunk-${chunk.id}`}
                        value={chunkDraft}
                        onChange={(event) => setChunkDraft(event.target.value)}
                        rows={8}
                        maxLength={100000}
                        className="w-full resize-y rounded-md border bg-background px-3 py-2 text-sm leading-6 outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        autoFocus
                      />
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                        <span className="text-xs text-muted-foreground">
                          {chunkDraft.length.toLocaleString()} / 100,000 字符
                        </span>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={cancelEditingChunk}
                            disabled={savingChunkId === chunk.id}
                          >
                            <X className="h-4 w-4" />
                            取消
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => saveChunk(chunk.id)}
                            disabled={savingChunkId === chunk.id || !chunkDraft.trim()}
                          >
                            {savingChunkId === chunk.id
                              ? <Loader2 className="h-4 w-4 animate-spin" />
                              : <Save className="h-4 w-4" />}
                            保存并重建索引
                          </Button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <p className="line-clamp-3 text-sm whitespace-pre-wrap">{chunk.content}</p>
                  )}
                </div>
              ))}
            </div>
          )}
          {chunkTotal > CHUNK_PAGE_SIZE && (
            <div className="flex items-center justify-between">
              <Button
                variant="outline"
                size="sm"
                disabled={chunkPage <= 1 || chunksLoading}
                onClick={() => fetchChunks(chunkPage - 1)}
              >
                上一页
              </Button>
              <span className="text-xs text-muted-foreground">
                第 {chunkPage} / {Math.ceil(chunkTotal / CHUNK_PAGE_SIZE)} 页
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={chunkPage >= Math.ceil(chunkTotal / CHUNK_PAGE_SIZE) || chunksLoading}
                onClick={() => fetchChunks(chunkPage + 1)}
              >
                下一页
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
