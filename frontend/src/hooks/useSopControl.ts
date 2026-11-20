import { useCallback } from 'react'
import { useApi } from './useWebSocket'
import type { ToastItem } from '../types'

type ShowToast = (text: string, type?: ToastItem['type']) => void

/**
 * SOP 控制操作
 * - 开始/暂停/重置/跳过
 * - 加载指定 SOP 文件
 * - 操作后自动刷新状态快照
 */
export function useSopControl(
  refreshStatus: () => Promise<void>,
  showToast: ShowToast,
) {
  const { call } = useApi()

  const handleStart = useCallback(async () => {
    await call('/sop/start')
    refreshStatus()
  }, [call, refreshStatus])

  const handlePause = useCallback(async () => {
    await call('/sop/pause')
    refreshStatus()
  }, [call, refreshStatus])

  const handleReset = useCallback(async () => {
    await call('/sop/reset')
    showToast('SOP 已重置', 'success')
    refreshStatus()
  }, [call, refreshStatus, showToast])

  const handleSkip = useCallback(async () => {
    await call('/sop/skip')
    refreshStatus()
    showToast('已跳过当前步骤', 'info')
  }, [call, refreshStatus, showToast])

  const handleLoadSop = useCallback(
    async (source: string) => {
      await call('/sop/load', { source })
      showToast(`已加载 SOP: ${source}`, 'success')
      refreshStatus()
    },
    [call, refreshStatus, showToast],
  )

  return { handleStart, handlePause, handleReset, handleSkip, handleLoadSop }
}
