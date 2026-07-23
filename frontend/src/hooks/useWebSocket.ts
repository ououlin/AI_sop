import { useEffect, useRef, useState, useCallback } from 'react'
import type { StatusMessage } from '../types'
import { apiFetch } from '../utils/api'

/**
 * 通用 WebSocket Hook
 * - 自动重连（指数退避 1s→2s→4s→8s 上限）
 * - 心跳保持（15s 发 ping）
 * - 通过 ref 持有 onMessage，避免变化导致重连
 */
function useSocket<T>(
  url: string,
  onMessage: (data: T) => void,
  onOpen?: () => void,
) {
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectCountRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const mountedRef = useRef(true)

  // 始终持有最新的 onMessage / onOpen，避免 effect 依赖变化导致重连
  const onMsgRef = useRef(onMessage)
  onMsgRef.current = onMessage
  const onOpenRef = useRef(onOpen)
  onOpenRef.current = onOpen

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (heartbeatTimerRef.current !== null) {
      clearInterval(heartbeatTimerRef.current)
      heartbeatTimerRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    clearTimers()

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}${url}`)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      reconnectCountRef.current = 0
      setConnected(true)
      onOpenRef.current?.()

      // 心跳：每 15s 发一次 ping
      heartbeatTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping')
        }
      }, 15000)
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setConnected(false)
      clearTimers()

      // 指数退避重连
      const delay = Math.min(1000 * 2 ** reconnectCountRef.current, 8000)
      reconnectCountRef.current += 1
      reconnectTimerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      ws.close()
    }

    ws.onmessage = (ev: MessageEvent) => {
      try {
        const data: T = JSON.parse(ev.data as string)
        onMsgRef.current(data)
      } catch {
        /* 非 JSON 消息（如 ping 回包）忽略 */
      }
    }
  }, [url, clearTimers])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      clearTimers()
      wsRef.current?.close()
    }
  }, [connect, clearTimers])

  return { connected }
}

/**
 * 视频帧 WebSocket Hook
 * 接收二进制 JPEG 帧，通过回调传出 blobURL
 */
export function useVideoSocket(onFrame: (dataUrl: string) => void) {
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectCountRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const mountedRef = useRef(true)
  const onFrameRef = useRef(onFrame)
  onFrameRef.current = onFrame

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (heartbeatTimerRef.current !== null) {
      clearInterval(heartbeatTimerRef.current)
      heartbeatTimerRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    clearTimers()

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/video`)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      reconnectCountRef.current = 0
      setConnected(true)
      heartbeatTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping')
        }
      }, 15000)
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setConnected(false)
      clearTimers()
      const delay = Math.min(1000 * 2 ** reconnectCountRef.current, 8000)
      reconnectCountRef.current += 1
      reconnectTimerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      ws.close()
    }

    ws.onmessage = (ev: MessageEvent) => {
      if (ev.data instanceof ArrayBuffer) {
        const blob = new Blob([ev.data], { type: 'image/jpeg' })
        const url = URL.createObjectURL(blob)
        onFrameRef.current(url)
      }
    }
  }, [clearTimers])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      clearTimers()
      wsRef.current?.close()
    }
  }, [connect, clearTimers])

  return { connected }
}

/**
 * 状态 WebSocket Hook
 * 接收步骤状态 + 手部信息
 */
export function useStatusSocket(onStatus: (status: StatusMessage) => void) {
  return useSocket<StatusMessage>('/ws/status', (msg) => {
    onStatus(msg)
  })
}

/**
 * REST API 调用封装
 * 支持 query 参数，自动携带 Authorization 头
 */
export function useApi() {
  const call = useCallback(
    async (path: string, params?: Record<string, string>) => {
      const url = new URL(`/api/v1${path}`, window.location.origin)
      if (params) {
        Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
      }
      const res = await apiFetch(url.pathname + url.search, { method: 'POST' })
      if (!res.ok) {
        throw new Error(`API ${path} 返回 ${res.status}`)
      }
      return res.json()
    },
    [],
  )
  return { call }
}
