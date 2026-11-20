import { useCallback, useEffect, useState } from 'react'
import { apiFetch, getActiveTenantId, setActiveTenantId } from '../utils/api'
import type { PlanInfo, TenantInfo } from '../types'

const STATUS_TEXT: Record<string, string> = {
  active: '启用',
  suspended: '已停用',
}

const EMPTY_FORM = {
  code: '',
  name: '',
  admin_username: '',
  admin_password: '',
  plan_code: 'free',
}

/**
 * 平台管理：租户开通、套餐变更、启停用与租户切换。
 * 仅拥有 tenant:manage 权限的平台管理员能看到该面板。
 */
export default function TenantManagement() {
  const [tenants, setTenants] = useState<TenantInfo[]>([])
  const [plans, setPlans] = useState<PlanInfo[]>([])
  const [form, setForm] = useState({ ...EMPTY_FORM })
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const activeTenant = getActiveTenantId()

  const load = useCallback(async () => {
    const [tenantResp, planResp] = await Promise.all([apiFetch('/tenants'), apiFetch('/plans')])
    if (tenantResp.ok) {
      setTenants((await tenantResp.json()) as TenantInfo[])
    }
    if (planResp.ok) {
      setPlans((await planResp.json()) as PlanInfo[])
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const run = async (action: () => Promise<Response>, okText: string): Promise<boolean> => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const resp = await action()
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        setError(
          (body.detail as string) ||
            (body.error as string) ||
            `操作失败（HTTP ${resp.status}）`,
        )
        return false
      }
      setMessage(okText)
      await load()
      return true
    } catch {
      setError('网络错误，请检查后端服务')
      return false
    } finally {
      setBusy(false)
    }
  }

  const createTenant = async (event: React.FormEvent) => {
    event.preventDefault()
    const ok = await run(
      () => apiFetch('/tenants', { method: 'POST', body: JSON.stringify(form) }),
      `租户 ${form.code} 已开通`,
    )
    if (ok) setForm({ ...EMPTY_FORM })
  }

  const changePlan = (tenant: TenantInfo, planCode: string) => {
    void run(
      () =>
        apiFetch(`/tenants/${tenant.id}/subscription`, {
          method: 'PUT',
          body: JSON.stringify({ plan_code: planCode }),
        }),
      `${tenant.code} 已切换到 ${planCode}`,
    )
  }

  const toggleStatus = (tenant: TenantInfo) => {
    void run(
      () =>
        apiFetch(`/tenants/${tenant.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ status: tenant.status === 'active' ? 'suspended' : 'active' }),
        }),
      `${tenant.code} 状态已更新`,
    )
  }

  const enterTenant = (tenant: TenantInfo) => {
    setActiveTenantId(tenant.id)
    window.location.reload()
  }

  const exitTenant = () => {
    setActiveTenantId(null)
    window.location.reload()
  }

  return (
    <div className="tenant-admin">
      {activeTenant !== null && (
        <div className="tenant-context">
          <span>正在以租户 #{activeTenant} 的视角查看数据</span>
          <button type="button" onClick={exitTenant}>退出切换</button>
        </div>
      )}
      {error && <div className="tenant-alert error">{error}</div>}
      {message && <div className="tenant-alert ok">{message}</div>}

      <div className="tenant-table-wrap">
        <table className="tenant-table">
          <thead>
            <tr>
              <th>编码</th>
              <th>名称</th>
              <th>状态</th>
              <th>套餐</th>
              <th>用户</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {tenants.map((tenant) => (
              <tr key={tenant.id}>
                <td>{tenant.code}</td>
                <td>{tenant.name}</td>
                <td>
                  <span className={`tenant-status ${tenant.status}`}>
                    {STATUS_TEXT[tenant.status] ?? tenant.status}
                  </span>
                </td>
                <td>
                  <select
                    value={tenant.plan_code}
                    disabled={busy}
                    onChange={(event) => changePlan(tenant, event.target.value)}
                  >
                    {plans.map((plan) => (
                      <option key={plan.code} value={plan.code}>{plan.name}</option>
                    ))}
                  </select>
                </td>
                <td>{tenant.user_count ?? '-'}</td>
                <td className="tenant-actions">
                  <button type="button" onClick={() => enterTenant(tenant)}>进入</button>
                  <button type="button" onClick={() => toggleStatus(tenant)}>
                    {tenant.status === 'active' ? '停用' : '启用'}
                  </button>
                </td>
              </tr>
            ))}
            {tenants.length === 0 && (
              <tr>
                <td colSpan={6} className="tenant-empty">暂无租户</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <form className="tenant-form" onSubmit={createTenant}>
        <input
          value={form.code}
          onChange={(event) => setForm({ ...form, code: event.target.value })}
          placeholder="租户编码（小写字母开头）"
          required
        />
        <input
          value={form.name}
          onChange={(event) => setForm({ ...form, name: event.target.value })}
          placeholder="租户名称"
          required
        />
        <input
          value={form.admin_username}
          onChange={(event) => setForm({ ...form, admin_username: event.target.value })}
          placeholder="管理员账号"
          required
        />
        <input
          type="password"
          value={form.admin_password}
          onChange={(event) => setForm({ ...form, admin_password: event.target.value })}
          placeholder="管理员密码（≥6 位）"
          required
        />
        <select
          value={form.plan_code}
          onChange={(event) => setForm({ ...form, plan_code: event.target.value })}
        >
          {plans.map((plan) => (
            <option key={plan.code} value={plan.code}>{plan.name}</option>
          ))}
        </select>
        <button type="submit" disabled={busy}>开通租户</button>
      </form>
    </div>
  )
}
