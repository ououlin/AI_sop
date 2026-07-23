import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../utils/api'

interface ZoneDef {
  [name: string]: [number, number, number, number]
}

interface ZoneColors {
  [name: string]: [number, number, number]
}

interface Props {
  /** 视频帧数据 URL，用于在画面上叠加标定矩形 */
  videoDataUrl?: string
}

/**
 * 区域标定工具（仅管理员可用）
 * 在视频画面上拖拽画矩形，持久化工作区域到后端 data/zones.json
 */
export default function ZoneCalibrator({ videoDataUrl }: Props) {
  const [zones, setZones] = useState<ZoneDef>({})
  const [colors, setColors] = useState<ZoneColors>({})
  const [editing, setEditing] = useState(false)
  const [msg, setMsg] = useState('')
  const imgRef = useRef<HTMLImageElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const dragRef = useRef<{ name: string; x0: number; y0: number; x1: number; y1: number } | null>(null)

  useEffect(() => {
    loadZones()
  }, [])

  // 视频帧更新时重绘叠加层
  useEffect(() => {
    drawOverlay()
  }, [videoDataUrl, zones])

  const loadZones = async () => {
    try {
      const resp = await apiFetch('/sop/zones', { method: 'GET' })
      if (resp.ok) {
        const data = await resp.json()
        setZones(data.zones || {})
        setColors(data.colors || {})
      }
    } catch (e) {
      // 静默
    }
  }

  const drawOverlay = () => {
    const canvas = canvasRef.current
    const img = imgRef.current
    if (!canvas || !img) return
    const w = img.clientWidth
    const h = img.clientHeight
    if (w === 0 || h === 0) return
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, w, h)

    for (const [name, coords] of Object.entries(zones)) {
      const [x1, y1, x2, y2] = coords
      const px = x1 * w
      const py = y1 * h
      const pw = (x2 - x1) * w
      const ph = (y2 - y1) * h
      const bgr = colors[name] || [100, 200, 255]
      ctx.strokeStyle = `rgb(${bgr[2]}, ${bgr[1]}, ${bgr[0]})`
      ctx.lineWidth = 2
      ctx.strokeRect(px, py, pw, ph)
      ctx.fillStyle = `rgba(${bgr[2]}, ${bgr[1]}, ${bgr[0]}, 0.12)`
      ctx.fillRect(px, py, pw, ph)
      ctx.fillStyle = '#fff'
      ctx.font = '12px sans-serif'
      ctx.fillText(name, px + 4, py + 14)
    }
  }

  const onMouseDown = (e: React.MouseEvent) => {
    if (!editing) return
    const canvas = canvasRef.current!
    const rect = canvas.getBoundingClientRect()
    const x = (e.clientX - rect.left) / canvas.width
    const y = (e.clientY - rect.top) / canvas.height
    const name = `zone_${Date.now().toString().slice(-4)}`
    dragRef.current = { name, x0: x, y0: y, x1: x, y1: y }
  }

  const onMouseMove = (e: React.MouseEvent) => {
    if (!editing || !dragRef.current) return
    const canvas = canvasRef.current!
    const rect = canvas.getBoundingClientRect()
    dragRef.current.x1 = (e.clientX - rect.left) / canvas.width
    dragRef.current.y1 = (e.clientY - rect.top) / canvas.height
    // 实时预览
    const d = dragRef.current
    setZones((prev) => ({
      ...prev,
      [d.name]: [
        Math.min(d.x0, d.x1),
        Math.min(d.y0, d.y1),
        Math.max(d.x0, d.x1),
        Math.max(d.y0, d.y1),
      ],
    }))
  }

  const onMouseUp = () => {
    dragRef.current = null
  }

  const handleSave = async () => {
    const zoneList = Object.entries(zones).map(([name, c]) => ({
      name,
      x_min: c[0],
      y_min: c[1],
      x_max: c[2],
      y_max: c[3],
    }))
    try {
      const resp = await apiFetch('/sop/zones', {
        method: 'POST',
        body: JSON.stringify({ zones: zoneList }),
      })
      if (resp.ok) {
        setMsg('区域已保存，重启后端生效')
        setTimeout(() => setMsg(''), 3000)
      } else {
        const err = await resp.json()
        setMsg(`保存失败: ${err.detail || '未知错误'}`)
      }
    } catch (e) {
      setMsg('网络错误')
    }
  }

  const handleDelete = (name: string) => {
    setZones((prev) => {
      const next = { ...prev }
      delete next[name]
      return next
    })
  }

  const handleReset = () => {
    loadZones()
  }

  return (
    <div className="zone-calibrator">
      <div className="zone-toolbar">
        <button
          className={editing ? 'btn-active' : ''}
          onClick={() => setEditing(!editing)}
        >
          {editing ? '完成标定' : '开始标定'}
        </button>
        <button onClick={handleSave}>保存区域</button>
        <button onClick={handleReset}>重置</button>
        {msg && <span className="zone-msg">{msg}</span>}
      </div>

      <div className="zone-canvas-wrap">
        <img
          ref={imgRef}
          src={videoDataUrl || '/api/v1/video/snapshot'}
          alt="标定画面"
          className="zone-bg"
          onLoad={drawOverlay}
        />
        <canvas
          ref={canvasRef}
          className={`zone-overlay ${editing ? 'editing' : ''}`}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={onMouseUp}
        />
      </div>

      {editing && (
        <p className="zone-hint">在画面上按住鼠标拖拽绘制矩形区域</p>
      )}

      <div className="zone-list">
        {Object.entries(zones).map(([name, c]) => (
          <div key={name} className="zone-item">
            <span className="zone-name">{name}</span>
            <span className="zone-coords">
              ({c[0].toFixed(2)}, {c[1].toFixed(2)}) - ({c[2].toFixed(2)}, {c[3].toFixed(2)})
            </span>
            <button className="zone-del" onClick={() => handleDelete(name)}>
              删除
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
