import { useState, useEffect, useRef } from 'react'

interface ControlPanelProps {
  onStart: () => Promise<void>
  onPause: () => Promise<void>
  onReset: () => Promise<void>
  onSkip: () => Promise<void>
  paused: boolean
}

/**
 * 控制面板（乐观更新）
 * 点击按钮后立即切换本地状态，消除远端同步延迟导致的"点了没反应"
 */
export function ControlPanel({
  onStart,
  onPause,
  onReset,
  onSkip,
  paused,
}: ControlPanelProps) {
  const [localPaused, setLocalPaused] = useState(paused)
  const [pending, setPending] = useState<string | null>(null)
  const mountedRef = useRef(true)

  // 与外部 paused 同步（仅在非 pending 状态时）
  useEffect(() => {
    if (!pending) {
      setLocalPaused(paused)
    }
  }, [paused, pending])

  useEffect(() => {
    return () => {
      mountedRef.current = false
    }
  }, [])

  const action = async (name: string, fn: () => Promise<void>) => {
    setPending(name)
    // 乐观切换
    if (name === 'pause') setLocalPaused(true)
    if (name === 'start') setLocalPaused(false)
    try {
      await fn()
    } catch {
      // 回滚
      setLocalPaused(paused)
    } finally {
      if (mountedRef.current) setPending(null)
    }
  }

  const isPaused = pending === 'pause' || (localPaused && pending !== 'start')
  const btnDisabled = (name: string) =>
    pending !== null &&
    pending !== name

  return (
    <div className="control-panel panel-card">
      <h3>控制面板</h3>
      <div className="btn-group">
        <button
          className="btn btn-start"
          disabled={!isPaused || btnDisabled('start')}
          onClick={() => action('start', onStart)}
        >
          {pending === 'start' ? '...' : '▶'} 开始 / 恢复
        </button>
        <button
          className="btn btn-pause"
          disabled={isPaused || btnDisabled('pause')}
          onClick={() => action('pause', onPause)}
        >
          {pending === 'pause' ? '...' : '⏸'} 暂停
        </button>
        <button
          className="btn btn-skip"
          disabled={btnDisabled('skip')}
          onClick={() => action('skip', onSkip)}
        >
          ⏭ 跳过当前
        </button>
        <button
          className="btn btn-reset"
          disabled={btnDisabled('reset')}
          onClick={() => action('reset', onReset)}
        >
          ↻ 重置
        </button>
      </div>
    </div>
  )
}
