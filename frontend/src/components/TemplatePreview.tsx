import type { MarketTemplateDetail } from '../types'

const ZONE_TEXT: Record<string, string> = {
  left_area: '左侧物料区',
  center_area: '中央工作台',
  right_area: '右侧成品区',
  top_area: '上方区域',
}

const GESTURE_TEXT: Record<string, string> = {
  open: '张开',
  fist: '握拳',
  pinch: '捏合',
  point: '指向',
  unknown: '不限',
}

export default function TemplatePreview({ detail }: { detail: MarketTemplateDetail }) {
  return (
    <div className="template-preview">
      <div className="template-preview-head">
        <div>
          <h3>{detail.name}</h3>
          <p>{detail.summary}</p>
        </div>
        <div className="template-tags">
          <span className="template-tag">{detail.industry}</span>
          <span className="template-tag">{detail.difficulty}</span>
          <span className="template-tag">{detail.step_count} 步</span>
        </div>
      </div>

      <table className="template-steps">
        <thead>
          <tr>
            <th>#</th>
            <th>步骤</th>
            <th>区域</th>
            <th>手势</th>
            <th>持续</th>
            <th>物体</th>
            <th>超时</th>
          </tr>
        </thead>
        <tbody>
          {detail.steps.map((step) => (
            <tr key={step.step_id}>
              <td>{step.step_id}</td>
              <td>
                <strong>{step.name}</strong>
                {step.description && <small>{step.description}</small>}
              </td>
              <td>{ZONE_TEXT[step.target_zone] ?? step.target_zone}</td>
              <td>{GESTURE_TEXT[step.required_gesture] ?? step.required_gesture}</td>
              <td>{step.hold_duration_sec.toFixed(1)}s</td>
              <td>
                {step.required_objects.length
                  ? step.required_objects
                      .map((item) => `${item.class_name}×${item.min_count}`)
                      .join('、')
                  : '-'}
              </td>
              <td>{Math.round(step.timeout_sec)}s</td>
            </tr>
          ))}
        </tbody>
      </table>

      {detail.recommended_objects.length > 0 && (
        <p className="template-hint">
          建议检测类别：{detail.recommended_objects.join('、')}
        </p>
      )}
    </div>
  )
}
