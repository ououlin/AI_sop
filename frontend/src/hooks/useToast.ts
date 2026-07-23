import { useCallback, useRef, useState } from 'react'
import type { ToastItem } from '../types'

/**
 * Toast 消息系统
 * - 最多保留 5 条
 * - 每条 3 秒后自动移除
 */
export function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const toastIdRef = useRef(0)

  const showToast = useCallback(
    (text: string, type: ToastItem['type'] = 'info') => {
      const id = ++toastIdRef.current
      setToasts((prev) => {
        const next = [...prev, { id, text, type }]
        return next.length > 5 ? next.slice(-5) : next
      })
      setTimeout(
        () => setToasts((prev) => prev.filter((t) => t.id !== id)),
        3000,
      )
    },
    [],
  )

  return { toasts, showToast }
}
