/**
 * KAI 知识 SSE 流式问答 API 客户端
 *
 * 运行：
 * KAI_KNOWLEDGE_API_KEY="你的密钥" node KAI知识流式问答API.mjs "平台如何完成清算？"
 */

const API_URL =
  process.env.KAI_KNOWLEDGE_STREAM_URL ||
  "https://wiki.kai.com/api/v1/kai-knowledge/chat/stream"

export async function streamKAI({
  message,
  conversationId = null,
  language = "zh-CN",
  apiKey = process.env.KAI_KNOWLEDGE_API_KEY,
  onStatus = () => {},
  onDelta = () => {},
  onDone = () => {},
}) {
  if (!apiKey) {
    throw new Error("缺少环境变量 KAI_KNOWLEDGE_API_KEY")
  }
  if (!message?.trim()) {
    throw new Error("问题不能为空")
  }

  const response = await fetch(API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      message: message.trim(),
      conversation_id: conversationId,
      language,
    }),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || `请求失败：${response.status}`)
  }
  if (!response.body) {
    throw new Error("服务器未返回流式响应")
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let answer = ""
  let completed = null

  const handleBlock = (block) => {
    let event = "message"
    const dataLines = []

    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim()
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart())
    }
    if (!dataLines.length) return

    const data = JSON.parse(dataLines.join("\n"))
    if (event === "status") onStatus(data)
    if (event === "delta") {
      answer += data.content || ""
      onDelta(data.content || "", answer)
    }
    if (event === "done") {
      completed = { ...data, answer }
      onDone(completed)
    }
    if (event === "error") {
      throw new Error(data.detail || "流式问答失败")
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })

    let separator
    while ((separator = buffer.search(/\r?\n\r?\n/)) !== -1) {
      const block = buffer.slice(0, separator)
      const match = buffer.slice(separator).match(/^\r?\n\r?\n/)
      buffer = buffer.slice(separator + (match?.[0].length || 2))
      handleBlock(block)
    }
    if (done) break
  }

  if (buffer.trim()) handleBlock(buffer)
  return completed || { answer }
}

const question = process.argv.slice(2).join(" ").trim()
if (question) {
  try {
    const result = await streamKAI({
      message: question,
      onStatus: ({ elapsed_seconds }) => {
        process.stderr.write(`\r正在深度检索：${elapsed_seconds.toFixed(1)}s`)
      },
      onDelta: (content) => {
        process.stdout.write(content)
      },
    })
    process.stderr.write("\n")
    console.log("\n\n会话 ID：", result.conversation_id)
    console.log("执行 ID：", result.execution_id)
    console.log("查询时间：", `${result.elapsed_seconds}s`)
  } catch (error) {
    console.error(error instanceof Error ? error.message : error)
    process.exitCode = 1
  }
}
