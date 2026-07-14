import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

/** shadcn/ui 标准 cn() 工具：合并 Tailwind class。 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
