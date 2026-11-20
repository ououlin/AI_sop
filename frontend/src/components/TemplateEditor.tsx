import { useState } from 'react'
import { apiFetch } from '../utils/api'

interface EditorStep {
  name: string
  target_zone: string
  required_gesture: string
  hold_duration_sec: number
  timeout_sec: number
  description: string
}

const ZONES = [
  { value: 'left_area', label: '左侧物料区' },
  { value: 'center_area', label: '中央工作台' },
  { value: 'right_area', label: '右侧成品区' },
  { value: 'top_area', label: '上方区域' },
]

const GESTURES = [
  { value: 'pinch', label: '捏合' },
  { value: 'open', label: '张开' },
  { value: 'fist', label: '握拳' },
  { value: 'point', label: '指向' },
  { value: 'unknown', label: '不限' },
]

function emptyStep(): EditorStep {
  return {
    name: '',
    target_zone: 'center_area',
    required_gesture: 'unknown',
    hold_duration_sec: 1.0,
    timeout_sec: 60,
    description: '',
  }
}

interface TemplateEditorProps {
  onSaved?: () => void
  onCancel?: () => void
}

/** 可视化模板编辑器：填写模板信息与步骤，保存为租户自定义模板。 */
export default function TemplateEditor({ onSaved, onCancel }: TemplateEditorProps) {
  const [name, setName] = useState('')
  const [industry, setIndustry] = useState('自定义')
  const [difficulty, setDifficulty] = useState('基础')
  const [summary, setSummary] = useState('')
  const [steps, setSteps] = useState<EditorStep[]>([emptyStep()])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const updateStep = (index: number, patch: Partial<EditorStep>) => {
    setSteps((current) => current.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }

  const addStep = () => setSteps((current) => [...current, emptyStep()])
  const removeStep = (index: number) => setSteps((current) => current.filter((_, i) => i !== index))

  const save = async () => {
    setError('')
    if (!name.trim()) {
      setError('请填写模板名称')
      return
    }
    if (steps.length === 0) {
      setError('至少需要一个步骤')
      return
    }
    if (steps.some((step) => !step.name.trim())) {
      setError('每个步骤都需要名称')
      return
    }

    setBusy(true)
    try {
      const body = {
        name: name.trim(),
        industry: industry.trim() || '自定义',
        difficulty,
        summary: summary.trim(),
        sop: {
          sop_name: name.trim(),
          steps: steps.map((step, index) => ({
            step_id: index + 1,
            name: step.name.trim(),
            target_zone: step.target_zone,
            required_gesture: step.required_gesture,
            hold_duration_sec: Number(step.hold_duration_sec) || 0.5,
            timeout_sec: Number(step.timeout_sec) || 60,
            description: step.description.trim(),
          })),
        },
      }
      const resp = await apiFetch('/marketplace/templates', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        setError((data.detail as string) || `保存失败（HTTP ${resp.status}）`)
        return
      }
      onSaved?.()
    } catch {
      setError('网络错误，请检查后端服务')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="tpl-editor">
      <div className="tpl-editor-head">
        <h3>新建模板</h3>
        <span>保存后可在列表中一键应用</span>
      </div>

      {error && <div className="tenant-alert error">{error}</div>}

      <div className="tpl-editor-meta">
        <label>
          模板名称
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：一号线装配" />
        </label>
        <label>
          行业
          <input value={industry} onChange={(event) => setIndustry(event.target.value)} placeholder="电子装配" />
        </label>
        <label>
          难度
          <select value={difficulty} onChange={(event) => setDifficulty(event.target.value)}>
            <option value="基础">基础</option>
            <option value="进阶">进阶</option>
          </select>
        </label>
        <label className="wide">
          简介
          <input value={summary} onChange={(event) => setSummary(event.target.value)} placeholder="一句话说明这条工序" />
        </label>
      </div>

      <table className="template-steps tpl-editor-steps">
        <thead>
          <tr>
            <th>#</th>
            <th>步骤名称</th>
            <th>区域</th>
            <th>手势</th>
            <th>持续(s)</th>
            <th>超时(s)</th>
            <th>说明</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {steps.map((step, index) => (
            <tr key={index}>
              <td>{index + 1}</td>
              <td>
                <input value={step.name} onChange={(event) => updateStep(index, { name: event.target.value })} />
              </td>
              <td>
                <select value={step.target_zone} onChange={(event) => updateStep(index, { target_zone: event.target.value })}>
                  {ZONES.map((zone) => (
                    <option key={zone.value} value={zone.value}>{zone.label}</option>
                  ))}
                </select>
              </td>
              <td>
                <select value={step.required_gesture} onChange={(event) => updateStep(index, { required_gesture: event.target.value })}>
                  {GESTURES.map((gesture) => (
                    <option key={gesture.value} value={gesture.value}>{gesture.label}</option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  type="number"
                  step="0.5"
                  min="0.5"
                  value={step.hold_duration_sec}
                  onChange={(event) => updateStep(index, { hold_duration_sec: Number(event.target.value) })}
                />
              </td>
              <td>
                <input
                  type="number"
                  step="10"
                  min="10"
                  value={step.timeout_sec}
                  onChange={(event) => updateStep(index, { timeout_sec: Number(event.target.value) })}
                />
              </td>
              <td>
                <input value={step.description} onChange={(event) => updateStep(index, { description: event.target.value })} />
              </td>
              <td>
                <button
                  type="button"
                  className="tpl-remove"
                  onClick={() => removeStep(index)}
                  disabled={steps.length === 1}
                  title="删除该步骤"
                >
                  ×
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="tpl-editor-actions">
        <button type="button" className="tpl-add" onClick={addStep}>＋ 添加步骤</button>
        <button type="button" className="tpl-save" onClick={() => void save()} disabled={busy}>
          {busy ? '保存中...' : '保存模板'}
        </button>
        {onCancel && <button type="button" className="tpl-cancel" onClick={onCancel}>取消</button>}
      </div>
    </div>
  )
}
