import { useCallback, useEffect, useState } from 'react'
import type { SopStatus } from '../types'
import { apiFetch } from '../utils/api'

/**
 * SOP 状态快照与摄像头索引轮询
 * - 首屏拉取一次 SOP 状态（WS 兜底）
 * - 每 5 秒轮询 /api/v1/health 同步摄像头索引
 */
export function useSopStatus(enabled: boolean) {
  const [sopStatus, setSopStatus] = useState<SopStatus | null>(null)
  const [cameraIndex, setCameraIndex] = useState(0)

  const refreshStatus = useCallback(async () => {
    if (!enabled) return
    try {
      const res = await apiFetch('/sop/status')
      const data = await res.json()
      setSopStatus(data)
    } catch {
      // 静默
    }
  }, [enabled])

  useEffect(() => {
    if (enabled) refreshStatus()
  }, [refreshStatus])

  useEffect(() => {
    if (!enabled) return
    const fetchCameraIndex = async () => {
      try {
        const res = await fetch('/api/v1/health')
        const data = await res.json()
        setCameraIndex(data.camera_index)
      } catch {
        // 静默
      }
    }
    fetchCameraIndex()
    const interval = setInterval(fetchCameraIndex, 5000)
    return () => clearInterval(interval)
  }, [enabled])

  return { sopStatus, cameraIndex, refreshStatus }
}
