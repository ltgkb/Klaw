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
} from "lucide-react"
import { kbApi, type KBRead, type DocumentRead, type SearchHit } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

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

  // 检索
  const [query, setQuery] = useState("")
  const [searching, setSearching] = useState(false)
  const [hits, setHits] = useState<SearchHit[]>([])

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

  const handleSearch = async () => {
    if (!kbId || !query.trim()) return
    setSearching(true)
    try {
      const resp = await kbApi.search(kbId, { query, top_k: 10 })
      setHits(resp.data.hits)
    } catch {
      // 错误由拦截器处理
    } finally {
      setSearching(false)
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
    <div className="space-y-6">
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
          <CardDescription>支持 PDF / DOCX / XLSX / PPTX / TXT / MD / HTML / JSON</CardDescription>
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
                    </div>
                    <div className={`flex items-center gap-1 text-xs ${status.color}`}>
                      <StatusIcon className={`h-3.5 w-3.5 ${doc.parse_status === "parsing" && "animate-spin"}`} />
                      {status.label}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDeleteDoc(doc.id)}
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
              onChange={(e) => setQuery(e.target.value)}
              placeholder="输入检索内容..."
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
            <Button onClick={handleSearch} disabled={searching || !query.trim()}>
              {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              检索
            </Button>
          </div>

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
                    </span>
                  </div>
                  <p className="text-sm whitespace-pre-wrap">{hit.content}</p>
                </div>
              ))}
            </div>
          )}

          {hits.length === 0 && query && !searching && (
            <p className="text-sm text-muted-foreground">无匹配结果</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
