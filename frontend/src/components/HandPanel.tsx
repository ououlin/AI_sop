import type { HandResult } from '../types'

interface HandPanelProps {
  hands: HandResult[]
  connected: boolean
}

const GESTURE_LABELS: Record<string, string> = {
  open: '张开',
  fist: '握拳',
  pinch: '捏合',
  point: '指向',
  unknown: '未知',
}

const GESTURE_ICONS: Record<string, string> = {
  open: '🖐',
  fist: '✊',
  pinch: '🤏',
  point: '☝',
  unknown: '❓',
}

const ZONE_NAMES: Record<string, string> = {
  zone_a: 'A 区',
  zone_b: 'B 区',
  zone_c: 'C 区',
  unknown: '未知区域',
}

export function HandPanel({ hands, connected }: HandPanelProps) {
  return (
    <div className="hand-panel panel-card">
      <h3>
        手部识别
        <span className={`mini-dot ${connected ? 'ok' : 'err'}`} />
      </h3>
      {!connected ? (
        <p className="empty">状态未连接</p>
      ) : hands.length === 0 ? (
        <p className="empty">画面中未检测到手部</p>
      ) : (
        <div className="hand-cards">
          {hands.map((hand, i) => (
            <div key={i} className="hand-card">
              <div className="hand-card-header">
                <span className="hand-icon">
                  {GESTURE_ICONS[hand.gesture] ?? '❓'}
                </span>
                <div className="hand-info">
                  <span className="hand-type">
                    {hand.handedness === 'Left' ? '左手' : '右手'}
                  </span>
                  <span className="hand-gesture">
                    {GESTURE_LABELS[hand.gesture] ?? hand.gesture}
                  </span>
                </div>
              </div>
              <div className="hand-card-body">
                <div className="hand-stat">
                  <span className="stat-label">位置</span>
                  <span className="stat-value">
                    ({hand.center_x.toFixed(3)}, {hand.center_y.toFixed(3)})
                  </span>
                </div>
                <div className="hand-stat">
                  <span className="stat-label">区域</span>
                  <span className="stat-value zone">
                    {ZONE_NAMES[hand.current_zone] ?? hand.current_zone}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
