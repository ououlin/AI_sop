import type { TrendPoint } from '../../types'

const WIDTH = 640
const HEIGHT = 150
const PAD_X = 28
const PAD_TOP = 12
const PAD_BOTTOM = 22

/**
 * 轻量趋势图（无第三方图表库）：
 * 柱状 = 每日执行数，折线 = 当日一次通过率（FPY）。
 */
export default function TrendChart({ series }: { series: TrendPoint[] }) {
  if (series.length === 0) {
    return <div className="trend-empty">暂无趋势数据</div>
  }

  const maxRuns = Math.max(1, ...series.map((point) => point.runs))
  const plotWidth = WIDTH - PAD_X * 2
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM
  const slot = plotWidth / series.length
  const barWidth = Math.max(4, slot * 0.5)

  const points = series.map((point, index) => {
    const x = PAD_X + slot * index + slot / 2
    const fpy = point.fpy ?? 0
    const y = PAD_TOP + plotHeight * (1 - fpy)
    return { x, y, fpy: point.fpy, date: point.date }
  })
  const linePath = points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x},${point.y}`).join(' ')

  return (
    <svg className="trend-chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="执行量与一次通过率趋势">
      <line x1={PAD_X} y1={PAD_TOP + plotHeight} x2={WIDTH - PAD_X} y2={PAD_TOP + plotHeight} className="trend-axis" />
      {series.map((point, index) => {
        const height = (point.runs / maxRuns) * plotHeight
        const x = PAD_X + slot * index + (slot - barWidth) / 2
        const y = PAD_TOP + plotHeight - height
        return (
          <g key={point.date}>
            <rect x={x} y={y} width={barWidth} height={height} className="trend-bar" />
            {point.runs > 0 && (
              <text x={x + barWidth / 2} y={y - 3} className="trend-bar-label">
                {point.runs}
              </text>
            )}
          </g>
        )
      })}
      <path d={linePath} className="trend-line" />
      {points.map((point) => (
        <circle key={`dot-${point.date}`} cx={point.x} cy={point.y} r={2.5} className="trend-dot" />
      ))}
      {series.map((point, index) => {
        const show = index === 0 || index === series.length - 1 || index === Math.floor(series.length / 2)
        if (!show) return null
        const x = PAD_X + slot * index + slot / 2
        return (
          <text key={`label-${point.date}`} x={x} y={HEIGHT - 6} className="trend-x-label">
            {point.date.slice(5)}
          </text>
        )
      })}
    </svg>
  )
}
