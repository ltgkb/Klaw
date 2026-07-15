import { Brain, Database, GitBranch, Type, Bell, BrainCog } from "lucide-react"
import type { NodeType } from "@/lib/api"
import { cn } from "@/lib/utils"

const TOOLBOX_ITEMS: { type: NodeType; label: string; icon: typeof Brain; color: string }[] = [
  { type: "llm", label: "LLM 对话", icon: Brain, color: "border-blue-300 bg-blue-50 hover:bg-blue-100" },
  { type: "retrieval", label: "知识库检索", icon: Database, color: "border-purple-300 bg-purple-50 hover:bg-purple-100" },
  { type: "condition", label: "条件分支", icon: GitBranch, color: "border-amber-300 bg-amber-50 hover:bg-amber-100" },
  { type: "text", label: "文本拼接", icon: Type, color: "border-gray-300 bg-gray-50 hover:bg-gray-100" },
  { type: "notify", label: "消息推送", icon: Bell, color: "border-pink-300 bg-pink-50 hover:bg-pink-100" },
  { type: "memory", label: "记忆读写", icon: BrainCog, color: "border-teal-300 bg-teal-50 hover:bg-teal-100" },
]

interface Props {
  onAdd: (type: NodeType) => void
}

export function NodeToolbox({ onAdd }: Props) {
  return (
    <div className="flex w-44 flex-col border-r bg-secondary/20">
      <div className="border-b p-3">
        <p className="text-xs font-semibold text-muted-foreground">节点工具箱</p>
        <p className="mt-0.5 text-[10px] text-muted-foreground">点击添加到画布</p>
      </div>
      <div className="flex flex-col gap-2 p-3">
        {TOOLBOX_ITEMS.map((item) => (
          <button
            key={item.type}
            onClick={() => onAdd(item.type)}
            className={cn(
              "flex items-center gap-2 rounded-md border px-3 py-2 text-left text-sm transition-colors",
              item.color,
            )}
          >
            <item.icon className="h-4 w-4 shrink-0" />
            {item.label}
          </button>
        ))}
      </div>
    </div>
  )
}
