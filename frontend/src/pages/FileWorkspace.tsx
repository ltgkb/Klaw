import { useEffect, useRef, useState } from "react"
import { Download, File, Link, Loader2, Trash2, Upload } from "lucide-react"
import { fileApi, type WorkspaceFile } from "@/lib/api"
import { Button } from "@/components/ui/button"

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function FileWorkspace() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<WorkspaceFile[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")

  const loadFiles = async () => {
    try {
      const { data } = await fileApi.list()
      setFiles(data)
      setError("")
    } catch {
      setError("无法加载文件，请稍后重试")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadFiles()
  }, [])

  const handleUpload = async (file: globalThis.File) => {
    setUploading(true)
    setNotice("")
    try {
      await fileApi.upload(file)
      await loadFiles()
      setNotice("上传完成")
    } catch {
      setError("上传失败，请检查文件大小或存储服务")
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  const handleDownload = async (item: WorkspaceFile) => {
    setBusyId(item.id)
    try {
      const { data } = await fileApi.download(item.id)
      const url = URL.createObjectURL(data)
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = item.filename
      anchor.click()
      URL.revokeObjectURL(url)
      setError("")
    } catch {
      setError("下载失败，请稍后重试")
    } finally {
      setBusyId(null)
    }
  }

  const handleShare = async (item: WorkspaceFile) => {
    setBusyId(item.id)
    try {
      const { data } = await fileApi.share(item.id)
      await navigator.clipboard.writeText(data.url)
      setNotice(`分享链接已复制，有效期 ${data.expires_hours} 小时`)
      setError("")
    } catch {
      setError("分享链接生成失败，请稍后重试")
    } finally {
      setBusyId(null)
    }
  }

  const handleDelete = async (item: WorkspaceFile) => {
    if (!confirm(`确认删除「${item.filename}」？`)) return
    setBusyId(item.id)
    try {
      await fileApi.delete(item.id)
      setFiles((current) => current.filter((file) => file.id !== item.id))
      setNotice("文件已删除")
      setError("")
    } catch {
      setError("删除失败，文件已保留，可稍后重试")
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">文件工作区</h1>
          <p className="mt-1 text-sm text-muted-foreground">{files.length} 个文件</p>
        </div>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          onChange={(event) => event.target.files?.[0] && handleUpload(event.target.files[0])}
        />
        <Button onClick={() => inputRef.current?.click()} disabled={uploading}>
          {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          上传文件
        </Button>
      </div>

      {error && <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</div>}
      {notice && <div role="status" className="rounded-md border bg-secondary/40 px-4 py-3 text-sm">{notice}</div>}

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : files.length === 0 ? (
        <div className="flex flex-col items-center justify-center border-y py-20 text-center">
          <File className="h-10 w-10 text-muted-foreground" />
          <p className="mt-3 text-sm text-muted-foreground">工作区暂无文件</p>
        </div>
      ) : (
        <div className="divide-y border-y">
          {files.map((item) => (
            <div key={item.id} className="flex min-w-0 items-center gap-3 py-4">
              <File className="h-5 w-5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium" title={item.filename}>{item.filename}</p>
                <p className="text-xs text-muted-foreground">{formatSize(item.file_size)} · {new Date(item.created_at).toLocaleString()}</p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button variant="ghost" size="sm" title="下载" aria-label={`下载 ${item.filename}`} disabled={busyId === item.id} onClick={() => handleDownload(item)}>
                  <Download className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="sm" title="复制分享链接" aria-label={`分享 ${item.filename}`} disabled={busyId === item.id} onClick={() => handleShare(item)}>
                  <Link className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="sm" title="删除" aria-label={`删除 ${item.filename}`} disabled={busyId === item.id} onClick={() => handleDelete(item)}>
                  {busyId === item.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4 text-destructive" />}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
