import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../utils/api'
import type { MarketModel, MarketTemplate, MarketTemplateDetail } from '../types'
import TemplatePreview from './TemplatePreview'

interface TemplateLibraryProps {
  canEdit: boolean
  onApplied?: () => void
}

export default function TemplateLibrary({ canEdit, onApplied }: TemplateLibraryProps) {
  const [templates, setTemplates] = useState<MarketTemplate[]>([])
  const [models, setModels] = useState<MarketModel[]>([])
  const [industry, setIndustry] = useState('全部')
  const [detail, setDetail] = useState<MarketTemplateDetail | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const [templateResp, modelResp] = await Promise.all([
      apiFetch('/marketplace/templates'),
      apiFetch('/marketplace/models'),
    ])
    if (templateResp.ok) setTemplates((await templateResp.json()) as MarketTemplate[])
    if (modelResp.ok) setModels((await modelResp.json()) as MarketModel[])
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const industries = useMemo(
    () => ['全部', ...Array.from(new Set(templates.map((item) => item.industry)))],
    [templates],
  )
  const visible = industry === '全部'
    ? templates
    : templates.filter((item) => item.industry === industry)

  const openDetail = async (templateId: string) => {
    setError('')
    setMessage('')
    const resp = await apiFetch(`/marketplace/templates/${templateId}`)
    if (!resp.ok) {
      setError('模板详情加载失败')
      return
    }
    setDetail((await resp.json()) as MarketTemplateDetail)
  }

  const apply = async () => {
    if (!detail) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const resp = await apiFetch(`/marketplace/templates/${detail.template_id}/apply`, {
        method: 'POST',
        body: JSON.stringify({ activate: true }),
      })
      const body = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        setError((body.detail as string) || `应用失败（HTTP ${resp.status}）`)
        return
      }
      setMessage(`已应用「${body.name}」并激活，当前 SOP 已切换`)
      onApplied?.()
    } catch {
      setError('网络错误，请检查后端服务')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="template-library">
      <div className="template-toolbar">
        {industries.map((item) => (
          <button
            key={item}
            type="button"
            className={`template-chip ${industry === item ? 'active' : ''}`}
            onClick={() => setIndustry(item)}
          >
            {item}
          </button>
        ))}
      </div>

      {error && <div className="tenant-alert error">{error}</div>}
      {message && <div className="tenant-alert ok">{message}</div>}

      <div className="template-grid">
        {visible.map((template) => (
          <button
            key={template.template_id}
            type="button"
            className={`template-card ${detail?.template_id === template.template_id ? 'selected' : ''}`}
            onClick={() => void openDetail(template.template_id)}
          >
            <span className="template-card-industry">{template.industry}</span>
            <strong>{template.name}</strong>
            <span className="template-card-summary">{template.summary}</span>
            <span className="template-card-meta">
              {template.step_count} 步 · {template.difficulty}
            </span>
          </button>
        ))}
        {visible.length === 0 && <div className="tenant-empty">该行业暂无模板</div>}
      </div>

      {detail && (
        <>
          <TemplatePreview detail={detail} />
          <div className="template-actions">
            <button type="button" disabled={!canEdit || busy} onClick={() => void apply()}>
              {busy ? '应用中...' : canEdit ? '应用并激活' : '需要 sop:edit 权限'}
            </button>
            <span className="template-hint">应用后会写入本租户数据库并立即切换当前 SOP</span>
          </div>
        </>
      )}

      {models.length > 0 && (
        <details className="template-models">
          <summary>检测模型目录（{models.length}）</summary>
          <table>
            <thead>
              <tr>
                <th>模型</th>
                <th>任务</th>
                <th>来源</th>
                <th>许可</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              {models.map((model) => (
                <tr key={model.model_id}>
                  <td>{model.name}</td>
                  <td>{model.task}</td>
                  <td>{model.source}</td>
                  <td>{model.license}</td>
                  <td>{model.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  )
}
