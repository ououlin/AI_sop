import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../utils/api'
import type { DeviceHealth, ModelVersionInfo } from '../types'

const HEALTH_TEXT: Record<string, string> = {
  healthy: '正常',
  warning: '告警',
  offline: '离线',
}

export default function DeviceManagement() {
  const [devices, setDevices] = useState<DeviceHealth[]>([])
  const [summary, setSummary] = useState({ total: 0, healthy: 0, warning: 0, offline: 0 })
  const [versions, setVersions] = useState<ModelVersionInfo[]>([])
  const [selected, setSelected] = useState<DeviceHealth | null>(null)
  const [interval, setIntervalValue] = useState('2.0')
  const [target, setTarget] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const [deviceResp, versionResp] = await Promise.all([
      apiFetch('/ops/devices'),
      apiFetch('/ops/model-versions'),
    ])
    if (deviceResp.ok) {
      const body = await deviceResp.json()
      setDevices(body.devices as DeviceHealth[])
      setSummary(body.summary)
    }
    if (versionResp.ok) {
      const list = (await versionResp.json()) as ModelVersionInfo[]
      setVersions(list)
      if (!target && list.length > 0) setTarget(`${list[0].model_id}@${list[0].version}`)
    }
  }, [target])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), 10000)
    return () => window.clearInterval(timer)
  }, [load])

  const refreshDetail = async (deviceId: string) => {
    const resp = await apiFetch(`/ops/devices/${deviceId}`)
    if (resp.ok) {
      const detail = (await resp.json()) as DeviceHealth
      setSelected(detail)
    }
  }

  const run = async (action: () => Promise<Response>, okText: string) => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const resp = await action()
      const body = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        setError((body.detail as string) || `操作失败（HTTP ${resp.status}）`)
        return false
      }
      setMessage(okText)
      await load()
      if (selected) await refreshDetail(selected.device_id)
      return true
    } catch {
      setError('网络错误，请检查后端服务')
      return false
    } finally {
      setBusy(false)
    }
  }

  const pushConfig = () => {
    if (!selected) return
    const value = Number(interval)
    if (!Number.isFinite(value) || value <= 0) {
      setError('上报间隔需为大于 0 的数字')
      return
    }
    void run(
      () =>
        apiFetch(`/ops/devices/${selected.device_id}/config`, {
          method: 'POST',
          body: JSON.stringify({ config: { report_interval: value } }),
        }),
      `已向 ${selected.device_id} 下发配置，等待工位回执`,
    )
  }

  const pushUpgrade = () => {
    if (!selected || !target) return
    const [modelId, version] = target.split('@')
    void run(
      () =>
        apiFetch(`/ops/devices/${selected.device_id}/upgrade`, {
          method: 'POST',
          body: JSON.stringify({ model_id: modelId, version }),
        }),
      `已向 ${selected.device_id} 下发升级指令（重启后生效）`,
    )
  }

  const modelOptions = useMemo(
    () => versions.map((item) => ({
      value: `${item.model_id}@${item.version}`,
      label: `${item.model_id} ${item.version}（${item.channel}）`,
    })),
    [versions],
  )

  return (
    <div className="device-admin">
      <div className="device-summary">
        <span className="device-chip">共 {summary.total} 台</span>
        <span className="device-chip ok">正常 {summary.healthy}</span>
        <span className="device-chip warn">告警 {summary.warning}</span>
        <span className="device-chip err">离线 {summary.offline}</span>
        <button type="button" className="device-refresh" onClick={() => void load()} disabled={busy}>
          刷新
        </button>
      </div>

      {error && <div className="tenant-alert error">{error}</div>}
      {message && <div className="tenant-alert ok">{message}</div>}

      <div className="tenant-table-wrap">
        <table className="tenant-table">
          <thead>
            <tr>
              <th>设备</th>
              <th>健康</th>
              <th>版本</th>
              <th>摄像头</th>
              <th>FPS</th>
              <th>延迟</th>
              <th>待执行</th>
              <th>最后心跳</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((device) => (
              <tr
                key={device.device_id}
                className={selected?.device_id === device.device_id ? 'device-row selected' : 'device-row'}
                onClick={() => void refreshDetail(device.device_id)}
              >
                <td>
                  <strong>{device.device_id}</strong>
                  <small>{device.name}</small>
                </td>
                <td>
                  <span className={`device-health ${device.health}`}>
                    {HEALTH_TEXT[device.health] ?? device.health}
                  </span>
                  {device.issues.length > 0 && <small>{device.issues.join('；')}</small>}
                </td>
                <td>
                  {device.model_version || '-'}
                  <small>{device.app_version}</small>
                </td>
                <td>{device.camera_ok ? '正常' : '异常'}</td>
                <td>{device.fps.toFixed(1)}</td>
                <td>{device.latency_ms.toFixed(0)}ms</td>
                <td>{device.pending_commands}</td>
                <td>{new Date(device.last_heartbeat).toLocaleTimeString()}</td>
              </tr>
            ))}
            {devices.length === 0 && (
              <tr>
                <td colSpan={8} className="tenant-empty">暂无设备上报</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="device-panel">
          <div className="section-heading">
            <h2>{selected.device_id} · 远程操作</h2>
            <span>{selected.health === 'healthy' ? '在线正常' : HEALTH_TEXT[selected.health]}</span>
          </div>

          <div className="device-actions">
            <label>
              上报间隔（秒）
              <input value={interval} onChange={(event) => setIntervalValue(event.target.value)} inputMode="decimal" />
            </label>
            <button type="button" disabled={busy} onClick={pushConfig}>下发配置</button>

            <label>
              目标版本
              <select value={target} onChange={(event) => setTarget(event.target.value)}>
                {modelOptions.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </label>
            <button type="button" disabled={busy} onClick={pushUpgrade}>下发升级</button>
          </div>

          {selected.last_ack && (
            <p className="template-hint">
              最近回执：{selected.last_ack.type} / {selected.last_ack.status} · {selected.last_ack.message || '无消息'}
            </p>
          )}

          {selected.commands && selected.commands.length > 0 && (
            <table className="template-steps">
              <thead>
                <tr><th>命令</th><th>类型</th><th>状态</th><th>载荷</th></tr>
              </thead>
              <tbody>
                {selected.commands.slice(-5).map((command) => (
                  <tr key={command.command_id}>
                    <td>{command.command_id}</td>
                    <td>{command.type}</td>
                    <td>{command.status}</td>
                    <td>{JSON.stringify(command.payload)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
