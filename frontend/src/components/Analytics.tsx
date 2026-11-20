import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../utils/api'
import type { AnalyticsOverview, SopStat, StepStat, TrendPoint } from '../types'
import TrendChart from './charts/TrendChart'

function percent(value: number | null | undefined) {
  if (value === null || value === undefined) return '-'
  return `${(value * 100).toFixed(2)}%`
}

function seconds(value: number | null | undefined) {
  if (value === null || value === undefined) return '-'
  if (value < 60) return `${value.toFixed(1)}s`
  return `${(value / 60).toFixed(1)}min`
}

export default function Analytics() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [series, setSeries] = useState<TrendPoint[]>([])
  const [steps, setSteps] = useState<StepStat[]>([])
  const [sops, setSops] = useState<SopStat[]>([])
  const [error, setError] = useState('')
  const [days, setDays] = useState(7)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (windowDays: number) => {
    setLoading(true)
    setError('')
    try {
      const [overviewResp, trendResp, stepResp, sopResp] = await Promise.all([
        apiFetch(`/analytics/overview?days=${windowDays}`),
        apiFetch(`/analytics/trend?days=${Math.max(windowDays, 7)}`),
        apiFetch('/analytics/steps?days=30&limit=8'),
        apiFetch('/analytics/sops?days=30'),
      ])
      if (!overviewResp.ok) {
        setError(`指标加载失败（HTTP ${overviewResp.status}）`)
        return
      }
      setOverview((await overviewResp.json()) as AnalyticsOverview)
      if (trendResp.ok) setSeries(((await trendResp.json()).series ?? []) as TrendPoint[])
      if (stepResp.ok) setSteps(((await stepResp.json()).steps ?? []) as StepStat[])
      if (sopResp.ok) setSops(((await sopResp.json()).sops ?? []) as SopStat[])
    } catch {
      setError('网络错误，请检查后端服务')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(days)
  }, [load, days])

  const oeeDetail = overview?.oee_detail

  return (
    <div className="analytics">
      <div className="analytics-toolbar">
        <span className="template-hint">统计窗口</span>
        {[7, 14, 30].map((option) => (
          <button
            key={option}
            type="button"
            className={`template-chip ${days === option ? 'active' : ''}`}
            onClick={() => setDays(option)}
          >
            {option} 天
          </button>
        ))}
        <button type="button" className="device-refresh" onClick={() => void load(days)} disabled={loading}>
          {loading ? '加载中...' : '刷新'}
        </button>
      </div>

      {error && <div className="tenant-alert error">{error}</div>}

      <div className="metric-grid">
        <div className="metric-card">
          <span>OEE（近似）</span>
          <strong>{percent(overview?.oee)}</strong>
          <small>
            可用 {percent(oeeDetail?.availability)} · 表现 {percent(oeeDetail?.performance)} · 质量 {percent(oeeDetail?.quality)}
          </small>
        </div>
        <div className="metric-card">
          <span>FPY 一次通过率</span>
          <strong>{percent(overview?.fpy)}</strong>
          <small>{overview?.completed_runs ?? 0} / {overview?.total_runs ?? 0} 次执行</small>
        </div>
        <div className="metric-card">
          <span>CT 平均节拍</span>
          <strong>{seconds(overview?.cycle_time_sec)}</strong>
          <small>失败 {overview?.failed_runs ?? 0} 次</small>
        </div>
        <div className="metric-card">
          <span>DPMO</span>
          <strong>{overview?.dpmo ?? '-'}</strong>
          <small>异常步骤 {overview?.defect_steps ?? 0} / 机会 {overview?.step_opportunities ?? 0}</small>
        </div>
        <div className="metric-card">
          <span>MTBF</span>
          <strong>{seconds(overview?.mtbf_sec)}</strong>
          <small>覆盖时长 {seconds(overview?.coverage_sec)}</small>
        </div>
      </div>

      <p className="template-hint">
        OEE = 可用率（窗口内执行覆盖）× 表现指数（最快节拍 / 平均节拍）× 一次通过率；统计窗口内覆盖时长不足时数值偏低属正常。
      </p>

      <div className="panel-card">
        <div className="section-heading">
          <h2>执行趋势</h2>
          <span>柱：执行数 · 线：FPY</span>
        </div>
        <TrendChart series={series} />
      </div>

      <div className="analytics-tables">
        <div className="panel-card">
          <div className="section-heading"><h2>瓶颈步骤</h2><span>按平均耗时</span></div>
          <table className="template-steps">
            <thead>
              <tr><th>步骤</th><th>次数</th><th>平均</th><th>最长</th><th>异常</th></tr>
            </thead>
            <tbody>
              {steps.map((step) => (
                <tr key={step.step_name}>
                  <td>{step.step_name}</td>
                  <td>{step.count}</td>
                  <td>{seconds(step.avg_duration_sec)}</td>
                  <td>{seconds(step.max_duration_sec)}</td>
                  <td>{step.defects}</td>
                </tr>
              ))}
              {steps.length === 0 && <tr><td colSpan={5} className="tenant-empty">暂无步骤数据</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="panel-card">
          <div className="section-heading"><h2>SOP 对比</h2><span>近 30 天</span></div>
          <table className="template-steps">
            <thead>
              <tr><th>SOP</th><th>执行</th><th>FPY</th><th>平均节拍</th></tr>
            </thead>
            <tbody>
              {sops.map((sop) => (
                <tr key={sop.sop_name}>
                  <td>{sop.sop_name}</td>
                  <td>{sop.runs}</td>
                  <td>{percent(sop.fpy)}</td>
                  <td>{seconds(sop.avg_duration_sec)}</td>
                </tr>
              ))}
              {sops.length === 0 && <tr><td colSpan={4} className="tenant-empty">暂无执行记录</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
