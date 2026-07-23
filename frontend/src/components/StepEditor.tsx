import { useState } from 'react'

export interface SOPStep {
  step_id: number
  name: string
  target_zone: string
  required_gesture: string
  hold_duration_sec: number
  description: string
}

interface StepEditorProps {
  step: SOPStep
  onUpdate: (step: SOPStep) => void
  onDelete: (stepId: number) => void
}

const zones = [
  { value: 'left_area', label: '左区域' },
  { value: 'center_area', label: '中区域' },
  { value: 'right_area', label: '右区域' },
  { value: 'top_area', label: '上区域' },
]

const gestures = [
  { value: 'open', label: '五指张开 (OPEN)' },
  { value: 'fist', label: '握拳 (FIST)' },
  { value: 'pinch', label: '捏合 (PINCH)' },
  { value: 'point', label: '指向 (POINT)' },
  { value: 'unknown', label: '不限手势' },
]

export function StepEditor({ step, onUpdate, onDelete }: StepEditorProps) {
  const [editing, setEditing] = useState(false)
  const [localStep, setLocalStep] = useState(step)

  const handleSave = () => {
    onUpdate(localStep)
    setEditing(false)
  }

  const handleCancel = () => {
    setLocalStep(step)
    setEditing(false)
  }

  if (!editing) {
    return (
      <div className="step-editor">
        <div className="step-header">
          <span className="step-id">#{step.step_id}</span>
          <span className="step-name">{step.name}</span>
          <button className="btn btn-sm" onClick={() => setEditing(true)}>编辑</button>
          <button className="btn btn-sm btn-danger" onClick={() => onDelete(step.step_id)}>删除</button>
        </div>
        <div className="step-info">
          <span className="step-zone">区域: {zones.find(z => z.value === step.target_zone)?.label}</span>
          <span className="step-gesture">手势: {gestures.find(g => g.value === step.required_gesture)?.label}</span>
          <span className="step-duration">持续: {step.hold_duration_sec}s</span>
        </div>
        {step.description && <p className="step-desc">{step.description}</p>}
      </div>
    )
  }

  return (
    <div className="step-editor editing">
      <div className="step-form">
        <div className="form-row">
          <label>步骤名称</label>
          <input
            type="text"
            value={localStep.name}
            onChange={(e) => setLocalStep({ ...localStep, name: e.target.value })}
          />
        </div>
        <div className="form-row">
          <label>目标区域</label>
          <select
            value={localStep.target_zone}
            onChange={(e) => setLocalStep({ ...localStep, target_zone: e.target.value })}
          >
            {zones.map(z => (
              <option key={z.value} value={z.value}>{z.label}</option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <label>需要手势</label>
          <select
            value={localStep.required_gesture}
            onChange={(e) => setLocalStep({ ...localStep, required_gesture: e.target.value })}
          >
            {gestures.map(g => (
              <option key={g.value} value={g.value}>{g.label}</option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <label>持续时长 (秒)</label>
          <input
            type="number"
            min="0.5"
            step="0.5"
            value={localStep.hold_duration_sec}
            onChange={(e) => setLocalStep({ ...localStep, hold_duration_sec: parseFloat(e.target.value) || 1 })}
          />
        </div>
        <div className="form-row">
          <label>描述</label>
          <textarea
            value={localStep.description}
            onChange={(e) => setLocalStep({ ...localStep, description: e.target.value })}
            rows={2}
          />
        </div>
        <div className="form-actions">
          <button className="btn" onClick={handleSave}>保存</button>
          <button className="btn btn-secondary" onClick={handleCancel}>取消</button>
        </div>
      </div>
    </div>
  )
}