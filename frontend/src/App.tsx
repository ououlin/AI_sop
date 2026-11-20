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
import TenantManagement from './components/TenantManagement'
import TemplateLibrary from './components/TemplateLibrary'
import DeviceManagement from './components/DeviceManagement'
import Analytics from './components/Analytics'
import { getActiveTenantId, setActiveTenantId } from './utils/api'
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
  const [assistantInput, setAssistantInput] = useState('')
  const [assistantMessages, setAssistantMessages] = useState<Array<{ role: 'agent' | 'user'; text: string }>>([
    { role: 'agent', text: '你好，我是智序助手。可以帮你查看工序进度、连接状态，或执行开始、暂停和重置。' },
  ])

  // WebSocket 连接
  const onFrame = useCallback(
    (url: string) => {
      if (videoSource === 'websocket') {
        setDataUrl(url)
      }
    },
    [videoSource],
  )
  const { connected: videoConn } = useVideoSocket(Boolean(auth), onFrame)
  const { connected: statusConn } = useStatusSocket(Boolean(auth), (msg: StatusMessage) =>
    setStatus(msg),
  )

  useEffect(() => {
    if (auth && videoSource === 'mjpeg') {
      setDataUrl(`/api/v1/video/mjpeg`)
    } else {
      setDataUrl('')
    }
  }, [auth, videoSource])

  useEffect(() => {
    if (!auth) setStatus(null)
  }, [auth])

  const videoState: ConnectionState = videoConn ? 'connected' : 'disconnected'
  const statusState: ConnectionState = statusConn ? 'connected' : 'disconnected'

  // SOP 状态快照与摄像头轮询
  const { sopStatus, cameraIndex, refreshStatus } = useSopStatus(Boolean(auth))

  // 控制操作
  const { handleStart, handlePause, handleReset, handleSkip, handleLoadSop } =
    useSopControl(refreshStatus, showToast)

  // 合并数据源（WS 为主，REST 快照为兜底）
  const steps = status?.steps ?? sopStatus?.steps ?? []
  const currentIndex =
    status?.current_step_index ?? sopStatus?.current_step_index ?? 0
  const allDone = status?.all_done ?? sopStatus?.all_done ?? false
  const sopName = status?.sop_name ?? sopStatus?.sop_name ?? ''
  const currentSource = status?.source ?? sopStatus?.source ?? ''
  const hands = status?.hands ?? []
  const fps = status?.fps ?? 0
  const paused = status?.paused ?? sopStatus?.paused ?? true
  const can = (permission: string) => auth?.permissions.includes(permission) ?? false
  const activeTenant = getActiveTenantId()

  const assistantReply = (question: string) => {
    const q = question.toLowerCase()
    if (q.includes('进度') || q.includes('步骤')) {
      const completed = steps.filter((step) => step.status === 'completed').length
      return `当前 SOP「${sopName || '未加载'}」已完成 ${completed}/${steps.length || 0} 步，${allDone ? '全部工序已完成。' : `正在处理第 ${currentIndex + 1} 步：${steps[currentIndex]?.name || '等待开始'}。`}`
    }
    if (q.includes('摄像头') || q.includes('视频') || q.includes('连接')) {
      return `视频${videoConn || videoSource === 'mjpeg' ? '已连接' : '未连接'}，状态通道${statusConn ? '正常' : '正在重连'}，当前 ${fps.toFixed(1)} FPS。`
    }
    if (q.includes('手') || q.includes('动作')) {
      return hands.length ? `检测到 ${hands.length} 只手，${hands.map((hand) => hand.handedness === 'Left' ? '左手' : '右手').join('、')}正在参与操作。` : '当前画面未检测到手部，请确认摄像头视野和光线。'
    }
    return '我可以帮你查看当前进度、摄像头连接、手部识别状态，或执行开始、暂停、重置操作。'
  }

  const askAssistant = (question = assistantInput) => {
    const text = question.trim()
    if (!text) return
    setAssistantMessages((messages) => [...messages, { role: 'user', text }, { role: 'agent', text: assistantReply(text) }])
    setAssistantInput('')
  }

  return (
    <ErrorBoundary>
      <div className="app">
        {!auth && <Login onLogin={handleLogin} />}

        <ConnectionBar video={videoState} status={statusState} />

        <header className="app-header">
          <div className="brand-lockup">
            <div className="brand-mark">序</div>
            <div>
              <h1>智序质控</h1>
              <p>AI 装配工序智能体</p>
            </div>
          </div>
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
            {auth && <span className="user-chip">{auth.displayName}<button className="logout-btn" onClick={handleLogout}>退出</button></span>}
            {auth && <span className="badge info">租户 {auth.tenant}</span>}
            {auth && activeTenant !== null && (
              <span className="badge warn">
                上下文 #{activeTenant}
                <button
                  className="logout-btn"
                  onClick={() => { setActiveTenantId(null); window.location.reload() }}
                >退出</button>
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

        {auth && <main className="app-main">
          <div className="workspace-grid">
            <section className="workspace-primary">
              <VideoView
                dataUrl={dataUrl}
                connected={videoConn || videoSource === 'mjpeg'}
                fps={fps}
                videoSource={videoSource}
              />
              <div className="session-strip">
                <div>
                  <span className="eyebrow">当前任务</span>
                  <strong>{sopName || '等待加载 SOP'}</strong>
                </div>
                <div className="session-metrics">
                  <span><b>{steps.filter((step) => step.status === 'completed').length}</b> 已完成</span>
                  <span><b>{steps.length}</b> 总步骤</span>
                  <span className={allDone ? 'metric-success' : ''}>{allDone ? '已完成' : paused ? '待开始' : '进行中'}</span>
                </div>
              </div>
              <div className="panel-card thumbnails-card">
                <div className="section-heading"><h2>工序路线</h2><span>{currentIndex + 1} / {steps.length || 0}</span></div>
                <StepThumbnails steps={steps} currentIndex={currentIndex} allDone={allDone} />
              </div>
            </section>

            <aside className="workspace-sidebar">
              <section className="agent-panel panel-card">
                <div className="agent-heading"><div className="agent-avatar">AI</div><div><h2>智序助手</h2><p>实时理解你的装配现场</p></div><span className="agent-live"><i />在线</span></div>
                <div className="agent-messages">
                  {assistantMessages.slice(-4).map((message, index) => <div key={`${message.role}-${index}`} className={`agent-message ${message.role}`}>{message.text}</div>)}
                </div>
                <div className="quick-prompts"><button onClick={() => askAssistant('当前进度怎么样？')}>查看进度</button><button onClick={() => askAssistant('摄像头状态怎么样？')}>检查连接</button><button onClick={() => askAssistant('手部识别情况？')}>识别状态</button></div>
                <form className="agent-input" onSubmit={(event) => { event.preventDefault(); askAssistant() }}><input value={assistantInput} onChange={(event) => setAssistantInput(event.target.value)} placeholder="询问当前装配状态..." /><button type="submit" aria-label="发送">↑</button></form>
              </section>
              <section className="control-card panel-card">
                <div className="section-heading"><h2>执行控制</h2><span className={`state-pill ${paused ? 'paused' : 'running'}`}>{paused ? '已暂停' : '运行中'}</span></div>
                <ControlPanel onStart={handleStart} onPause={handlePause} onReset={handleReset} onSkip={handleSkip} paused={paused} canSkip={can('sop:skip')} />
              </section>
              <section className="panel-card compact-status"><div className="section-heading"><h2>当前步骤</h2><span>{steps[currentIndex]?.status === 'in_progress' ? '执行中' : '待执行'}</span></div><StepList steps={steps.slice(currentIndex, currentIndex + 1)} currentIndex={0} allDone={allDone} /></section>
            </aside>
          </div>

          <details className="tool-drawer">
            <summary><span>更多工作台工具</span><small>记录、SOP、摄像头与报告</small><b>展开</b></summary>
            <div className="tool-grid">
              <section className="panel-card"><div className="section-heading"><h2>SOP 管理</h2></div><SopSwitcher currentSource={currentSource} onLoad={handleLoadSop} />{can('sop:edit') && <SopEditor onSave={refreshStatus} />}</section>
              {can('sop:view') && <section className="panel-card tool-wide"><div className="section-heading"><h2>工序模板</h2><span>行业模板一键应用</span></div><TemplateLibrary canEdit={can('sop:edit')} onApplied={refreshStatus} /></section>}
              <section className="panel-card"><div className="section-heading"><h2>执行记录</h2></div><RecordList /></section>
              {can('camera:view') && <section className="panel-card"><div className="section-heading"><h2>摄像头</h2></div><CameraSelector currentIndex={cameraIndex} canManage={can('camera:manage')} />{can('camera:manage') && <ZoneCalibrator videoDataUrl={dataUrl} />}</section>}
              {can('record:export') && <section className="panel-card"><div className="section-heading"><h2>质检报告</h2></div><ReportExport /></section>}
              {can('line:view') && <section className="panel-card tool-wide"><div className="section-heading"><h2>产线看板</h2></div><LineDashboard /></section>}
              {can('record:view:all') && <section className="panel-card tool-wide"><div className="section-heading"><h2>数据看板</h2><span>OEE · FPY · 节拍 · 瓶颈</span></div><Analytics /></section>}
              {can('station:view') && <section className="panel-card tool-wide"><div className="section-heading"><h2>设备运维</h2><span>健康监控 · 配置下发 · 远程升级</span></div><DeviceManagement /></section>}
              {can('tenant:manage') && <section className="panel-card tool-wide"><div className="section-heading"><h2>平台管理</h2><span>租户与套餐</span></div><TenantManagement /></section>}
              <section className="panel-card"><div className="section-heading"><h2>手部识别</h2></div><HandPanel hands={hands} connected={statusConn} /></section>
            </div>
          </details>
        </main>}

        <ToastContainer toasts={toasts} />
      </div>
    </ErrorBoundary>
  )
}
