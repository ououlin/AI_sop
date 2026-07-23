import { Component } from 'react'
import type { ToastItem, ConnectionState } from '../types'

// ============ ErrorBoundary ============
interface EBState {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<
  { children: React.ReactNode },
  EBState
> {
  state: EBState = { hasError: false, error: null }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <h2>应用发生错误</h2>
          <pre>{this.state.error?.message}</pre>
          <button
            className="btn"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            重新加载
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

// ============ Toast 容器 ============
export function ToastContainer({ toasts }: { toasts: ToastItem[] }) {
  if (toasts.length === 0) return null
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          {t.text}
        </div>
      ))}
    </div>
  )
}

// ============ 连接状态栏 ============
export function ConnectionBar({
  video,
  status,
}: {
  video: ConnectionState
  status: ConnectionState
}) {
  const allOk = video === 'connected' && status === 'connected'
  const allDisconnected =
    video === 'disconnected' && status === 'disconnected'

  if (allOk) return null
  return (
    <div className={`connection-bar ${allDisconnected ? 'critical' : 'warn'}`}>
      <span className="conn-dot pulse" />
      视频:{' '}
      {video === 'connecting' ? '连接中' : video === 'disconnected' ? '已断开' : '正常'}
      &nbsp;&nbsp;|&nbsp;&nbsp;状态:{' '}
      {status === 'connecting' ? '连接中' : '已断开'}
      {allDisconnected && (
        <span className="conn-retry-hint">正在自动重连...</span>
      )}
    </div>
  )
}
