import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../utils/api'

export interface ExecutionRecord {
  id: number
  sop_name: string
  start_time: string | null
  end_time: string | null
  status: string
  total_duration: number
  step_count: number
}

interface RecordListProps {
  onSelect?: (record: ExecutionRecord) => void
}

export function RecordList({ onSelect }: RecordListProps) {
  const [records, setRecords] = useState<ExecutionRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  const refreshRecords = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiFetch(`/records/?page=${page}&limit=10`)
      const data = await res.json()
      setRecords(data.records || [])
      setTotal(data.total)
    } catch (e) {
      console.error('Failed to fetch records:', e)
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    refreshRecords()
  }, [refreshRecords])

  const formatTime = (isoString: string | null) => {
    if (!isoString) return '-'
    const date = new Date(isoString)
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  const formatDuration = (seconds: number) => {
    if (!seconds) return '-'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  return (
    <div className="record-list">
      <div className="panel-header">
        <span className="badge info">{total} 条</span>
      </div>

      {loading ? (
        <div className="loading">加载中...</div>
      ) : records.length === 0 ? (
        <p className="empty">暂无执行记录</p>
      ) : (
        <div className="records-table">
          <table>
            <thead>
              <tr>
                <th>SOP</th>
                <th>开始</th>
                <th>结束</th>
                <th>状态</th>
                <th>时长</th>
                <th>步骤</th>
              </tr>
            </thead>
            <tbody>
              {records.map((record) => (
                <tr
                  key={record.id}
                  className="record-row"
                  onClick={() => onSelect?.(record)}
                >
                  <td className="record-sop">{record.sop_name}</td>
                  <td className="record-time">{formatTime(record.start_time)}</td>
                  <td className="record-time">{formatTime(record.end_time)}</td>
                  <td>
                    <span className={`record-status ${record.status}`}>
                      {record.status === 'completed' ? '已完成' : record.status === 'in_progress' ? '进行中' : '已中断'}
                    </span>
                  </td>
                  <td className="record-duration">{formatDuration(record.total_duration)}</td>
                  <td className="record-steps">{record.step_count} 步</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {total > 10 && (
        <div className="pagination">
          <button
            className="btn btn-sm"
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page === 1}
          >
            上一页
          </button>
          <span className="page-info">{page} / {Math.ceil(total / 10)}</span>
          <button
            className="btn btn-sm"
            onClick={() => setPage(Math.min(Math.ceil(total / 10), page + 1))}
            disabled={page >= Math.ceil(total / 10)}
          >
            下一页
          </button>
        </div>
      )}
    </div>
  )
}