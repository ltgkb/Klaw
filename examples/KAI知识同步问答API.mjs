/**
 * KAI 知识同步问答 API 客户端
 *
 * 运行：
 * KAI_KNOWLEDGE_API_KEY="你的密钥" node KAI知识同步问答API.mjs "什么是期算平台？"
 */

const API_URL =
  process.env.KAI_KNOWLEDGE_SYNC_URL ||
  "https://wiki.kai.com/api/v1/kai-knowledge/chat"

export async function askKAI({
  message,
  conversationId = null,
  language = "zh-CN",
  apiKey = process.env.KAI_KNOWLEDGE_API_KEY,
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
    },
    body: JSON.stringify({
      message: message.trim(),
      conversation_id: conversationId,
      language,
    }),
  })

  const result = await response.json()
  if (!response.ok) {
    throw new Error(result.detail || `请求失败：${response.status}`)
  }
  return result
}

const question = process.argv.slice(2).join(" ").trim()
if (question) {
  try {
    const result = await askKAI({ message: question })
    console.log(result.answer)
    console.log("\n会话 ID：", result.conversation_id)
    console.log("执行 ID：", result.execution_id)
    console.log("查询时间：", `${result.elapsed_seconds}s`)
  } catch (error) {
    console.error(error instanceof Error ? error.message : error)
    process.exitCode = 1
  }
}
