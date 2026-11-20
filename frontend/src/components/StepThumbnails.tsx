import type { StepRuntimeState } from '../types'

interface StepThumbnailsProps {
  steps: StepRuntimeState[]
  currentIndex: number
  allDone: boolean
}

const STATUS_COLORS: Record<string, string> = {
  pending: '#475569',
  in_progress: '#3b82f6',
  completed: '#22c55e',
  skipped: '#94a3b8',
  timeout: '#ef4444',
  error: '#ef4444',
  unauthorized_skip: '#ef4444',
}

export function StepThumbnails({ steps, currentIndex, allDone }: StepThumbnailsProps) {
  if (steps.length === 0) {
    return (
      <div className="step-thumbnails">
        <p className="empty">未加载SOP</p>
      </div>
    )
  }

  return (
    <div className="step-thumbnails">
      {steps.map((step, index) => {
        const isActive = index === currentIndex && !allDone
        const isCompleted = step.status === 'completed'

        return (
          <div
            key={step.step_id}
            className={`step-thumbnail ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}
          >
            <div className="step-num">{index + 1}</div>
            <div className="step-info">
              <div className="step-name">{step.name}</div>
              <div className="step-status" style={{ backgroundColor: STATUS_COLORS[step.status] }}></div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
