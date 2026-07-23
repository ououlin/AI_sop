import { useCallback, useEffect, useState } from 'react'
import { useVideoSocket, useStatusSocket } from './hooks/useWebSocket'
import { useAuth } from './hooks/useAuth'
import { useToast } from './hooks/useToast'
import { useSopStatus } from './hooks/useSopStatus'
import { useSopControl } from './hooks/useSopControl'
import { ErrorBoundary, ToastContainer, ConnectionBar } from './components/ErrorBoundary'
import { VideoView, type VideoSourceType } from './components/VideoView'
import { StepList } from './components/StepList'
import { StepThumbnails } from './components/StepThumbnails'
import { ControlPanel } from './components/ControlPanel'
import { HandPanel } from './components/HandPanel'
import { SopSwitcher } from './components/SopSwitcher'
import { SopEditor } from './components/SopEditor'
import { RecordList } from './components/RecordList'
import { CameraSelector } from './components/CameraSelector'
import Login from './components/Login'
import LineDashboard from './components/LineDashboard'
import ReportExport from './components/ReportExport'
import ZoneCalibrator from './components/ZoneCalibrator'
import type { StatusMessage, ConnectionState } from './types'
import './index.css'

export default function App() {
  // 登录态
  const { auth, handleLogin, handleLogout } = useAuth()

  // Toast
  const { toasts, showToast } = useToast()

  // 视频源与实时数据
  const [dataUrl, setDataUrl] = useState('')
  const [status, setStatus] = useState<StatusMessage | null>(null)
  const [videoSource, setVideoSource] = useState<VideoSourceType>('websocket')

  // WebSocket 连接
  const onFrame = useCallback(
    (url: string) => {
      if (videoSource === 'websocket') {
        setDataUrl(url)
      }
    },
    [videoSource],
  )
  const { connected: videoConn } = useVideoSocket(onFrame)
  const { connected: statusConn } = useStatusSocket((msg: StatusMessage) =>
    setStatus(msg),
  )

  useEffect(() => {
    if (videoSource === 'mjpeg') {
      setDataUrl(`/api/v1/video/mjpeg`)
    } else {
      setDataUrl('')
    }
  }, [videoSource])

  const videoState: ConnectionState = videoConn ? 'connected' : 'disconnected'
  const statusState: ConnectionState = statusConn ? 'connected' : 'disconnected'

  // SOP 状态快照与摄像头轮询
  const { sopStatus, cameraIndex, refreshStatus } = useSopStatus()

  // 当前加载的 SOP 文件名（前端追踪）
  const [currentSopFile, setCurrentSopFile] = useState('')

  // 控制操作
  const { handleStart, handlePause, handleReset, handleSkip, handleLoadSop } =
    useSopControl(refreshStatus, showToast, setCurrentSopFile)

  // 合并数据源（WS 为主，REST 快照为兜底）
  const steps = status?.steps ?? sopStatus?.steps ?? []
  const currentIndex =
    status?.current_step_index ?? sopStatus?.current_step_index ?? 0
  const allDone = status
    ? status.steps.every((s) => s.status === 'completed' || s.status === 'skipped')
    : (sopStatus?.all_done ?? false)
  const sopName = status?.sop_name ?? sopStatus?.sop_name ?? ''
  const hands = status?.hands ?? []
  const fps = status?.fps ?? 0
  const paused = sopStatus?.paused ?? false

  return (
    <ErrorBoundary>
      <div className="app">
        {!auth && <Login onLogin={handleLogin} />}

        <ConnectionBar video={videoState} status={statusState} />

        <header className="app-header">
          <h1>AI SOP 装配线工序识别系统</h1>
          <div className="status-badges">
            <span className={`badge ${videoConn || videoSource === 'mjpeg' ? 'ok' : 'err'}`}>
              视频 {videoConn || videoSource === 'mjpeg' ? '已连接' : '断开'}
            </span>
            <span className={`badge ${statusConn ? 'ok' : 'err'}`}>
              状态 {statusConn ? '已连接' : '断开'}
            </span>
            {fps > 0 && (
              <span className="badge info">FPS: {fps.toFixed(1)}</span>
            )}
            {paused && <span className="badge warn">已暂停</span>}
            {auth && (
              <span className="badge info">
                {auth.displayName} ({auth.role})
                <button className="logout-btn" onClick={handleLogout}>退出</button>
              </span>
            )}
            <select
              className="video-source-select"
              value={videoSource}
              onChange={(e) => setVideoSource(e.target.value as VideoSourceType)}
            >
              <option value="websocket">WebSocket</option>
              <option value="mjpeg">MJPEG</option>
            </select>
          </div>
        </header>

        <main className="app-main">
          <div className="top-row">
            <section className="video-section">
              <VideoView
                dataUrl={dataUrl}
                connected={videoConn || videoSource === 'mjpeg'}
                fps={fps}
                videoSource={videoSource}
              />
              {sopName && (
                <div className="sop-title">
                  当前工序: <strong>{sopName}</strong>
                  {allDone && <span className="done-tag">全部完成</span>}
                </div>
              )}
            </section>

            <aside className="right-panel">
              <div className="panel-card">
                <h3>控制</h3>
                <ControlPanel
                  onStart={handleStart}
                  onPause={handlePause}
                  onReset={handleReset}
                  onSkip={handleSkip}
                  paused={paused}
                />
              </div>
              <div className="panel-card">
                <h3>步骤列表</h3>
                <StepList
                  steps={steps}
                  currentIndex={currentIndex}
                  allDone={allDone}
                />
              </div>
              <div className="panel-card">
                <h3>手部检测</h3>
                <HandPanel hands={hands} connected={statusConn} />
              </div>
              <div className="panel-card">
                <h3>SOP选择</h3>
                <SopSwitcher
                  currentFile={currentSopFile}
                  onLoad={handleLoadSop}
                />
              </div>
            </aside>
          </div>

          <div className="bottom-row">
            <div className="panel-card thumbnails-card">
              <h3>步骤预览</h3>
              <StepThumbnails
                steps={steps}
                currentIndex={currentIndex}
                allDone={allDone}
              />
            </div>
            <div className="panel-card">
              <h3>SOP编辑</h3>
              <SopEditor />
            </div>
            <div className="panel-card">
              <h3>执行记录</h3>
              <RecordList />
            </div>
            <div className="panel-card">
              <h3>摄像头</h3>
              <CameraSelector currentIndex={cameraIndex} />
            </div>
            <div className="panel-card report-card">
              <h3>质检报告</h3>
              <ReportExport />
            </div>
            {auth?.role === 'admin' && (
              <div className="panel-card zone-card">
                <h3>区域标定（管理员）</h3>
                <ZoneCalibrator videoDataUrl={dataUrl} />
              </div>
            )}
            <div className="panel-card dashboard-card">
              <h3>产线看板</h3>
              <LineDashboard />
            </div>
          </div>
        </main>

        <ToastContainer toasts={toasts} />
      </div>
    </ErrorBoundary>
  )
}
