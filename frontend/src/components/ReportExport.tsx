import { useState } from 'react';
import { apiFetch } from '../utils/api';

const statusClassMap: Record<string, string> = {
  '合格': 'completed',
  '已跳过': 'skipped',
  '未授权跳过': 'error',
  '超时': 'timeout',
  '错误': 'error',
  '未执行': 'pending',
  '进行中': 'in_progress',
};
const getStatusLabel = (status: string): string => statusClassMap[status] || 'pending';

export default function ReportExport() {
  const [operator, setOperator] = useState('');
  const [orderNo, setOrderNo] = useState('');
  const [productModel, setProductModel] = useState('');
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const generateReport = async () => {
    setLoading(true);
    try {
      const resp = await apiFetch('/reports/generate', {
        method: 'POST',
        body: JSON.stringify({ operator, order_no: orderNo, product_model: productModel }),
      });
      if (resp.ok) {
        const data = await resp.json();
        setReport(data);
      }
    } catch (e) {
      // 静默处理
    } finally {
      setLoading(false);
    }
  };

  const exportText = async () => {
    const resp = await apiFetch('/reports/export/text', {
      method: 'POST',
      body: JSON.stringify({ operator, order_no: orderNo, product_model: productModel }),
    });
    if (resp.ok) {
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${Date.now()}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const exportCsv = async () => {
    const resp = await apiFetch('/reports/export/csv', {
      method: 'POST',
      body: JSON.stringify({ operator, order_no: orderNo, product_model: productModel }),
    });
    if (resp.ok) {
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${Date.now()}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const exportPdf = async () => {
    const resp = await apiFetch('/reports/export/pdf', {
      method: 'POST',
      body: JSON.stringify({ operator, order_no: orderNo, product_model: productModel }),
    });
    if (resp.ok) {
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${Date.now()}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } else if (resp.status === 503) {
      alert('PDF 导出不可用：后端未安装 reportlab，请在 backend/ 执行 pip install reportlab');
    }
  };

  const exportExcel = async () => {
    const resp = await apiFetch('/reports/export/excel', {
      method: 'POST',
      body: JSON.stringify({ operator, order_no: orderNo, product_model: productModel }),
    });
    if (resp.ok) {
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${Date.now()}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } else if (resp.status === 503) {
      alert('Excel 导出不可用：后端未安装 openpyxl，请在 backend/ 执行 pip install openpyxl');
    }
  };

  return (
    <div className="report-export">
      <div className="report-form">
        <div className="form-row">
          <input
            placeholder="操作员"
            value={operator}
            onChange={(e) => setOperator(e.target.value)}
          />
          <input
            placeholder="订单号"
            value={orderNo}
            onChange={(e) => setOrderNo(e.target.value)}
          />
          <input
            placeholder="产品型号"
            value={productModel}
            onChange={(e) => setProductModel(e.target.value)}
          />
        </div>
        <div className="form-actions">
          <button onClick={generateReport} disabled={loading}>
            {loading ? '生成中...' : '生成报告'}
          </button>
          <button onClick={exportText}>导出TXT</button>
          <button onClick={exportCsv}>导出CSV</button>
          <button onClick={exportPdf}>导出PDF</button>
          <button onClick={exportExcel}>导出Excel</button>
        </div>
      </div>

      {report && (
        <div className="report-preview">
          <div className="report-header">
            <h3>{report.report_id}</h3>
            <span>{report.generated_at}</span>
          </div>
          <div className="report-meta">
            <span>SOP: {report.sop_name}</span>
            <span>操作员: {report.operator || '-'}</span>
          </div>
          <table className="report-table">
            <thead>
              <tr>
                <th>步骤</th>
                <th>名称</th>
                <th>开始</th>
                <th>结束</th>
                <th>用时</th>
                <th>结果</th>
              </tr>
            </thead>
            <tbody>
              {report.steps.map((s: any, i: number) => (
                <tr key={i}>
                  <td>{s.step_id}</td>
                  <td>{s.name}</td>
                  <td>{s.started_at}</td>
                  <td>{s.completed_at}</td>
                  <td>{s.duration}</td>
                  <td className={`status-${getStatusLabel(s.status)}`}>{s.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="report-summary">
            <span>合格率: {report.summary.pass_rate}%</span>
            <span>结论: <strong>{report.summary.conclusion}</strong></span>
          </div>
          {(report.alarms || []).length > 0 && (
            <div className="report-alarms">
              <h4>异常记录</h4>
              {(report.alarms || []).map((a: any, i: number) => (
                <div key={i} className={`alarm-row ${a.level}`}>
                  [{a.level}] {a.timestamp} {a.message}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
