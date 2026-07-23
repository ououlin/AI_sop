import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../utils/api';

interface StationInfo {
  station_id: string;
  station_name: string;
  status: string;
  sop_name: string;
  current_step_index: number;
  total_steps: number;
  current_step_name: string;
  step_status: string;
  matched_duration: number;
  hold_duration_sec: number;
  alarms: any[];
  fps: number;
  is_online: boolean;
  last_heartbeat: string;
}

interface LineSummary {
  total_stations: number;
  online_stations: number;
  running_stations: number;
  error_stations: number;
  active_alarms: number;
  timestamp: string;
}

const statusConfig: Record<string, { color: string; label: string; bg: string }> = {
  running: { color: '#52c41a', label: '运行中', bg: '#f6ffed' },
  paused: { color: '#faad14', label: '已暂停', bg: '#fffbe6' },
  idle: { color: '#8c8c8c', label: '空闲', bg: '#fafafa' },
  error: { color: '#ff4d4f', label: '异常', bg: '#fff2f0' },
  offline: { color: '#d9d9d9', label: '离线', bg: '#f5f5f5' },
};

export default function LineDashboard() {
  const [stations, setStations] = useState<StationInfo[]>([]);
  const [summary, setSummary] = useState<LineSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStations = useCallback(async () => {
    try {
      const resp = await apiFetch('/stations', { method: 'GET' });
      if (resp.ok) {
        const data = await resp.json();
        setStations(data.stations || []);
        setSummary(data.summary);
      }
    } catch (e) {
      // 静默处理
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStations();
    const timer = setInterval(fetchStations, 2000);
    return () => clearInterval(timer);
  }, [fetchStations]);

  if (loading) {
    return <div className="line-dashboard-loading">加载产线看板...</div>;
  }

  return (
    <div className="line-dashboard">
      <div className="dashboard-header">
        <h2>产线看板</h2>
        {summary && (
          <div className="summary-cards">
            <div className="summary-card">
              <span className="summary-value">{summary.total_stations}</span>
              <span className="summary-label">总工位</span>
            </div>
            <div className="summary-card online">
              <span className="summary-value">{summary.online_stations}</span>
              <span className="summary-label">在线</span>
            </div>
            <div className="summary-card running">
              <span className="summary-value">{summary.running_stations}</span>
              <span className="summary-label">运行中</span>
            </div>
            <div className="summary-card error">
              <span className="summary-value">{summary.error_stations}</span>
              <span className="summary-label">异常</span>
            </div>
            <div className="summary-card alarm">
              <span className="summary-value">{summary.active_alarms}</span>
              <span className="summary-label">活跃告警</span>
            </div>
          </div>
        )}
      </div>

      {stations.length === 0 ? (
        <div className="no-stations">
          暂无工位数据。请配置工位Agent并设置 CENTRAL_SERVER_URL 环境变量。
        </div>
      ) : (
        <div className="station-grid">
          {stations.map((station) => {
            const cfg = statusConfig[station.status] || statusConfig.idle;
            const progress = station.total_steps > 0
              ? (station.current_step_index / station.total_steps) * 100
              : 0;
            const hasAlarms = (station.alarms || []).length > 0;

            return (
              <div
                key={station.station_id}
                className={`station-card ${!station.is_online ? 'offline' : ''}`}
                style={{ borderLeftColor: cfg.color }}
              >
                <div className="station-header">
                  <span className="station-name">{station.station_name}</span>
                  <span
                    className="station-status"
                    style={{ color: cfg.color, backgroundColor: cfg.bg }}
                  >
                    {cfg.label}
                  </span>
                </div>

                <div className="station-body">
                  <div className="station-sop">
                    {station.sop_name || '未加载SOP'}
                  </div>

                  {station.status === 'running' && station.total_steps > 0 && (
                    <>
                      <div className="station-step">
                        步骤 {station.current_step_index + 1}/{station.total_steps}: {station.current_step_name}
                      </div>
                      <div className="progress-bar">
                        <div
                          className="progress-fill"
                          style={{ width: `${progress}%`, backgroundColor: cfg.color }}
                        />
                      </div>
                      <div className="step-status">{station.step_status}</div>
                    </>
                  )}

                  {hasAlarms && (
                    <div className="station-alarms">
                      {(station.alarms || []).slice(-2).map((a: any, i: number) => (
                        <div key={i} className={`alarm-item ${a.level}`}>
                          [{a.level}] {a.message}
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="station-footer">
                    <span>FPS: {station.fps.toFixed(1)}</span>
                    <span>{station.station_id}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
