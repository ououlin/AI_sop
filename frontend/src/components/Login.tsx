import { useState } from 'react';

interface LoginProps {
  onLogin: (
    token: string,
    role: string,
    displayName: string,
    permissions: string[],
    tenant: string,
    tenantId: number,
  ) => void;
}

const API_BASE = '/api/v1';

export default function Login({ onLogin }: LoginProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [tenant, setTenant] = useState('default');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, tenant: tenant.trim() || 'default' }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        setError(data.detail || data.error || '登录失败');
        return;
      }
      onLogin(
        data.access_token,
        data.role,
        data.display_name,
        data.permissions || [],
        data.tenant || 'default',
        data.tenant_id || 1,
      );
    } catch (e) {
      setError('网络错误，请检查服务是否启动');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-overlay">
      <form className="login-form" onSubmit={handleSubmit}>
        <div className="login-brand">
          <h2>智序质控</h2>
          <p>AI 装配工序智能体</p>
        </div>
        {error && <div className="login-error">{error}</div>}
        <div className="login-field">
          <label>租户编码</label>
          <input
            type="text"
            value={tenant}
            onChange={(e) => setTenant(e.target.value)}
            placeholder="default"
          />
        </div>
        <div className="login-field">
          <label>用户名</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="请输入用户名"
            required
          />
        </div>
        <div className="login-field">
          <label>密码</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="请输入密码"
            required
          />
        </div>
        <button type="submit" disabled={loading}>
          {loading ? '登录中...' : '登录'}
        </button>
        <div className="login-hint">
          默认租户 default 的账户: admin/admin123 | supervisor/super123 | operator/op123
        </div>
      </form>
    </div>
  );
}
