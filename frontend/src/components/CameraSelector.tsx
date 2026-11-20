import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../utils/api'

interface CameraInfo {
  index: number
  resolution: string
}

interface CameraSelectorProps {
  currentIndex: number
  canManage: boolean
}

export function CameraSelector({ currentIndex, canManage }: CameraSelectorProps) {
  const [cameras, setCameras] = useState<CameraInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(currentIndex)

  const refreshCameras = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiFetch('/camera/list')
      const data = await res.json()
      setCameras(data.cameras || [])
    } catch (e) {
      console.error('Failed to fetch cameras:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshCameras()
  }, [refreshCameras])

  useEffect(() => {
    setSelectedIndex(currentIndex)
  }, [currentIndex])

  const handleSwitch = async (index: number) => {
    if (index === selectedIndex) return
    try {
      const res = await apiFetch('/camera/switch', {
        method: 'POST',
        body: JSON.stringify({ index }),
      })
      const data = await res.json()
      if (data.status === 'success') {
        setSelectedIndex(index)
      }
    } catch (e) {
      console.error('Failed to switch camera:', e)
    }
  }

  return (
    <div className="camera-selector">
      <div className="panel-header">
        <button className="btn btn-sm" onClick={refreshCameras} disabled={loading}>
          {loading ? '刷新中...' : '刷新'}
        </button>
      </div>

      {loading ? (
        <div className="loading">检测中...</div>
      ) : cameras.length === 0 ? (
        <p className="empty">未检测到摄像头</p>
      ) : (
        <div className="camera-list">
          {cameras.map((cam) => (
            <button
              key={cam.index}
              className={`camera-item ${selectedIndex === cam.index ? 'active' : ''}`}
              disabled={!canManage}
              onClick={() => handleSwitch(cam.index)}
            >
              <span className="camera-index">摄像头 {cam.index}</span>
              <span className="camera-res">{cam.resolution}</span>
              {selectedIndex === cam.index && (
                <span className="camera-badge">当前</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
