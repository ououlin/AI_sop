import { useEffect, useRef, useCallback } from 'react'

export type VideoSourceType = 'websocket' | 'mjpeg'

interface VideoViewProps {
  dataUrl: string
  connected: boolean
  fps: number
  videoSource: VideoSourceType
}

/**
 * 视频渲染组件（生产级）
 * - Blob URL 替代 base64 dataURL，避免主线程阻塞
 * - requestAnimationFrame 节流绘制
 * - 及时 revokeObjectURL 防止内存泄漏
 * - 断线/加载/正常三态 UI
 */
export function VideoView({ dataUrl, connected, fps, videoSource }: VideoViewProps) {
  const imgRef = useRef<HTMLImageElement>(null)
  const prevBlobUrlRef = useRef<string | null>(null)
  const rafIdRef = useRef<number | null>(null)

  const revokePrevious = useCallback(() => {
    if (prevBlobUrlRef.current) {
      URL.revokeObjectURL(prevBlobUrlRef.current)
      prevBlobUrlRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!dataUrl) return

    if (videoSource === 'mjpeg') {
      if (imgRef.current) {
        imgRef.current.src = dataUrl
      }
      return
    }

    // websocket 模式：useVideoSocket 传入的是 blob URL（"blob:..."），
    // 浏览器原生支持将其作为 img.src 渲染，无需 atob 解码，避免主线程阻塞。
    // 兼容：若上游改为 base64 dataUrl，同样可直接赋值。
    rafIdRef.current = requestAnimationFrame(() => {
      if (imgRef.current) {
        imgRef.current.src = dataUrl
      }
      // 释放上一帧 blob URL，防止内存泄漏
      revokePrevious()
      prevBlobUrlRef.current = dataUrl.startsWith('blob:') ? dataUrl : null
    })

    return () => {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current)
        rafIdRef.current = null
      }
    }
  }, [dataUrl, revokePrevious, videoSource])

  useEffect(() => {
    return () => revokePrevious()
  }, [revokePrevious])

  return (
    <div className="video-view">
      {/* 视频画面 */}
      <img
        ref={imgRef}
        alt="实时视频"
        className="video-frame"
        style={{ display: dataUrl && connected ? 'block' : 'none', transform: 'scaleX(-1)' }}
      />

      {/* 断线占位 */}
      {!connected && (
        <div className="video-placeholder disconnected">
          <div className="spinner stopped" />
          <p>视频流已断开</p>
          <p className="hint">正在尝试重连...</p>
        </div>
      )}

      {/* 初始加载 */}
      {connected && !dataUrl && (
        <div className="video-placeholder">
          <div className="spinner" />
          <p>等待视频流...</p>
          <p className="hint">请确认后端服务已启动且摄像头已连接</p>
        </div>
      )}

      {/* FPS 角标 */}
      {connected && dataUrl && (
        <span className="fps-badge">{fps.toFixed(1)} FPS</span>
      )}
    </div>
  )
}
