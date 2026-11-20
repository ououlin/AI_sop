import { useState, useEffect, useCallback } from 'react'
import { StepEditor, type SOPStep } from './StepEditor'
import { apiFetch } from '../utils/api'

interface SopEditorProps {
  onSave?: () => void
}

const defaultStep: SOPStep = {
  step_id: 0,
  name: '',
  target_zone: 'center_area',
  required_gesture: 'unknown',
  hold_duration_sec: 1,
  description: '',
}

export function SopEditor({ onSave }: SopEditorProps) {
  const [sopName, setSopName] = useState('')
  const [version, setVersion] = useState('1.0')
  const [steps, setSteps] = useState<SOPStep[]>([])
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)

  const refreshList = useCallback(async () => {
    try {
      const res = await apiFetch('/sop/db/list')
      const data = await res.json()
      console.log('DB SOPs:', data)
    } catch (e) {
      console.error('Failed to fetch SOPs from DB:', e)
    }
  }, [])

  useEffect(() => {
    refreshList()
  }, [refreshList])

  const handleAddStep = () => {
    const newId = steps.length > 0 ? Math.max(...steps.map(s => s.step_id)) + 1 : 1
    setSteps([...steps, { ...defaultStep, step_id: newId }])
  }

  const handleUpdateStep = (updatedStep: SOPStep) => {
    setSteps(steps.map(s => s.step_id === updatedStep.step_id ? updatedStep : s))
    setSaved(false)
  }

  const handleDeleteStep = (stepId: number) => {
    setSteps(steps.filter(s => s.step_id !== stepId))
    setSaved(false)
  }

  const handleSave = async () => {
    if (!sopName.trim() || steps.length === 0) {
      alert('请填写SOP名称并添加至少一个步骤')
      return
    }

    setLoading(true)
    try {
      const res = await apiFetch('/sop/db/save', {
        method: 'POST',
        body: JSON.stringify({
          name: sopName,
          version,
          steps,
          activate: true,
        }),
      })
      if (res.ok) {
        const data = await res.json()
        console.log('Saved SOP:', data)
        setSaved(true)
        setTimeout(() => setSaved(false), 3000)
        onSave?.()
      } else {
        const error = await res.json()
        alert(`保存失败: ${error.detail || error.error || res.status}`)
      }
    } catch (e) {
      alert('保存失败，请检查后端服务')
    } finally {
      setLoading(false)
    }
  }

  const handleLoadFromFile = async () => {
    try {
      const res = await apiFetch('/sop/list')
      const data = await res.json()
      const fileEntry = (data.entries || []).find(
        (entry: { source: string }) => entry.source === 'file',
      )
      if (fileEntry) {
        const fileRes = await apiFetch(`/sop/file/${encodeURIComponent(fileEntry.name)}`)
        if (!fileRes.ok) throw new Error(`HTTP ${fileRes.status}`)
        const sopData = await fileRes.json()
        setSopName(sopData.sop_name || fileEntry.name.replace('.json', ''))
        setVersion(sopData.version || '1.0')
        setSteps(sopData.steps || [])
        setSaved(false)
      }
    } catch (e) {
      console.error('Failed to load SOP:', e)
    }
  }

  return (
    <div className="sop-editor">
      <div className="panel-header">
        <div className="panel-actions">
          <button className="btn btn-sm" onClick={handleLoadFromFile}>从文件加载</button>
          <button className={`btn btn-sm ${saved ? 'btn-success' : ''}`} onClick={handleSave} disabled={loading}>
            {loading ? '保存中...' : saved ? '已保存!' : '保存到数据库'}
          </button>
        </div>
      </div>

      <div className="editor-form">
        <div className="form-row">
          <label>SOP 名称</label>
          <input
            type="text"
            value={sopName}
            onChange={(e) => { setSopName(e.target.value); setSaved(false) }}
            placeholder="输入SOP名称"
          />
        </div>
        <div className="form-row">
          <label>版本</label>
          <input
            type="text"
            value={version}
            onChange={(e) => { setVersion(e.target.value); setSaved(false) }}
            placeholder="1.0"
          />
        </div>
      </div>

      <div className="steps-section">
        <div className="steps-header">
          <span>步骤列表 ({steps.length})</span>
          <button className="btn btn-sm" onClick={handleAddStep}>+ 添加步骤</button>
        </div>
        {steps.length === 0 ? (
          <p className="empty">暂无步骤，请点击上方按钮添加</p>
        ) : (
          <div className="steps-list">
            {steps.map((step) => (
              <StepEditor
                key={step.step_id}
                step={step}
                onUpdate={handleUpdateStep}
                onDelete={handleDeleteStep}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
