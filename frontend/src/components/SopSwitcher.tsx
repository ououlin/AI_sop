import { useState, useEffect, useCallback } from 'react'
import type { SopFileEntry } from '../types'
import { apiFetch } from '../utils/api'

interface SopSwitcherProps {
  currentSource: string
  onLoad: (source: string) => Promise<void>
}

export function SopSwitcher({ currentSource, onLoad }: SopSwitcherProps) {
  const [sops, setSops] = useState<SopFileEntry[]>([])
  const [loading, setLoading] = useState(false)

  const refreshList = useCallback(async () => {
    try {
      const res = await apiFetch('/sop/list')
      const data = await res.json()
      setSops((data.entries ?? []).map((entry: SopFileEntry) => ({
        ...entry,
        loaded: entry.key === currentSource,
      })))
    } catch {
      // 列表加载失败静默
    }
  }, [currentSource])

  useEffect(() => {
    refreshList()
  }, [refreshList])

  const handleLoad = async (source: string) => {
    setLoading(true)
    try {
      await onLoad(source)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="sop-switcher panel-card">
      <h3>SOP 切换</h3>
      {sops.length === 0 ? (
        <p className="empty">暂无可用的 SOP 文件</p>
      ) : (
        <div className="sop-select-list">
          {sops.map((sop) => {
            const isCurrent = sop.key === currentSource
            return (
              <button
                key={sop.key}
                className={`sop-select-item ${isCurrent ? 'current' : ''}`}
                disabled={loading || isCurrent}
                onClick={() => handleLoad(sop.key)}
                title={isCurrent ? '当前已加载' : `加载 ${sop.name}`}
              >
                <span className="sop-select-name">
                  {sop.name} <small>{sop.source === 'file' ? '文件' : '数据库'}</small>
                </span>
                {isCurrent && <span className="sop-current-tag">当前</span>}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
