import type { StepRuntimeState } from '../types'

interface StepListProps {
  steps: StepRuntimeState[]
  currentIndex: number
  allDone: boolean
}

const STATUS_LABEL: Record<string, string> = {
  pending: '待执行',
  in_progress: '进行中',
  completed: '已完成',
  skipped: '已跳过',
}

export function StepList({ steps, currentIndex, allDone }: StepListProps) {
  if (steps.length === 0) {
    return (
      <div className="step-list">
        <p className="empty">未加载SOP</p>
      </div>
    )
  }

  return (
    <div className="step-list">
      <ol>
        {steps.map((step, i) => {
          const isActive = i === currentIndex && !allDone
          const progress =
            step.hold_duration_sec > 0
              ? Math.min(
                  (step.matched_duration / step.hold_duration_sec) * 100,
                  100,
                )
              : 0

          return (
            <li
              key={step.step_id}
              className={`step-item ${step.status} ${isActive ? 'active' : ''}`}
            >
              <div className="step-header">
                <span className="step-no">
                  {step.status === 'completed' ? '✓' : i + 1}
                </span>
                <span className="step-name">{step.name}</span>
                <span className={`step-status ${step.status}`}>
                  {STATUS_LABEL[step.status] ?? step.status}
                </span>
              </div>
              {step.description && (
                <p className="step-desc">{step.description}</p>
              )}
              {/* 真实进度条 */}
              {step.status === 'in_progress' && (
                <div className="step-progress">
                  <div
                    className="step-progress-bar real"
                    style={{ width: `${Math.max(progress, 3)}%` }}
                  />
                  <span className="step-progress-text">
                    {progress.toFixed(0)}% ({step.matched_duration.toFixed(1)}s
                    / {step.hold_duration_sec.toFixed(1)}s)
                  </span>
                </div>
              )}
              {step.status === 'completed' && step.completed_at && (
                <p className="step-time">
                  完成于 {new Date(step.completed_at).toLocaleTimeString()}
                </p>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
