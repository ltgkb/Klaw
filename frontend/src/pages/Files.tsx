import { useEffect, useRef, useState } from "react"
import {
  Upload,
  Trash2,
  Download,
  Link2,
  Loader2,
  FileText,
  FolderOpen,
} from "lucide-react"
import { fileApi, type WorkspaceFile } from "@/lib/api"
import { toast } from "@/lib/toast"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function Files() {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<WorkspaceFile[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)

  const fetchFiles = async () => {
    setLoading(true)
    try {
      const resp = await fileApi.list()
      setFiles(resp.data)
    } catch {
      // 错误由拦截器处理
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchFiles()
  }, [])

  const handleUpload = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return
    setUploading(true)
    try {
      for (const file of Array.from(fileList)) {
        await fileApi.upload(file)
      }
      toast.success("上传成功")
      await fetchFiles()
    } catch {
      // 错误由拦截器处理
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  const handleDownload = async (file: WorkspaceFile) => {
    setDownloadingId(file.id)
    try {
      const resp = await fileApi.download(file.id)
      const url = URL.createObjectURL(resp.data)
      const a = document.createElement("a")
      a.href = url
      a.download = file.filename
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      // 错误由拦截器处理
    } finally {
      setDownloadingId(null)
    }
  }

  const handleDelete = async (file: WorkspaceFile) => {
    if (!confirm(`确认删除文件「${file.filename}」？`)) return
    try {
      await fileApi.delete(file.id)
      toast.success("已删除")
      await fetchFiles()
    } catch {
      // 错误由拦截器处理
    }
  }

  const handleShare = async (file: WorkspaceFile) => {
    try {
      const resp = await fileApi.share(file.id)
      await navigator.clipboard.writeText(resp.data.url)
      toast.success(`分享链接已复制 (${resp.data.expires_hours} 小时内有效)`)
    } catch {
      // 错误由拦截器处理
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">文件工作区</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          MinIO 对象存储 · 上传 / 下载 / 预签名分享链接
        </p>
      </div>

      {/* 上传 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">上传文件</CardTitle>
          <CardDescription>文件仅本人可见，可生成限时分享链接</CardDescription>
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
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
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

      {/* 文件列表 */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : files.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <FolderOpen className="h-12 w-12 text-muted-foreground" />
            <p className="mt-4 text-sm text-muted-foreground">工作区还没有文件</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">我的文件 ({files.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {files.map((file) => (
                <div key={file.id} className="flex items-center gap-3 rounded-md border p-3">
                  <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{file.filename}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatSize(file.file_size)} · {new Date(file.created_at).toLocaleString("zh-CN")}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    title="复制分享链接"
                    onClick={() => handleShare(file)}
                  >
                    <Link2 className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    title="下载"
                    disabled={downloadingId === file.id}
                    onClick={() => handleDownload(file)}
                  >
                    {downloadingId === file.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Download className="h-4 w-4" />
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    title="删除"
                    onClick={() => handleDelete(file)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
