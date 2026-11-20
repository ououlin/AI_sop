/**
 * API 请求工具函数
 * - 自动从 localStorage 读取 JWT Token 并设置 Authorization 头
 * - 平台管理员切换租户时，自动带上 X-Tenant-Id 头
 */

export function getAuthToken(): string | null {
  const saved = localStorage.getItem('ai_sop_auth')
  if (!saved) return null
  try {
    const parsed = JSON.parse(saved)
    return parsed.token || null
  } catch {
    return null
  }
}

function getAuthRole(): string | null {
  const saved = localStorage.getItem('ai_sop_auth')
  if (!saved) return null
  try {
    return JSON.parse(saved).role || null
  } catch {
    return null
  }
}

const ACTIVE_TENANT_KEY = 'ai_sop_active_tenant'

/** 平台管理员当前切入的租户 ID（仅对 platform_admin 生效） */
export function getActiveTenantId(): number | null {
  const saved = localStorage.getItem(ACTIVE_TENANT_KEY)
  if (!saved) return null
  const tenantId = Number(saved)
  return Number.isFinite(tenantId) && tenantId > 0 ? tenantId : null
}

export function setActiveTenantId(tenantId: number | null) {
  if (tenantId === null) {
    localStorage.removeItem(ACTIVE_TENANT_KEY)
    return
  }
  localStorage.setItem(ACTIVE_TENANT_KEY, String(tenantId))
}

export async function apiFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const token = getAuthToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const activeTenant = getActiveTenantId()
  if (activeTenant !== null && getAuthRole() === 'platform_admin') {
    headers['X-Tenant-Id'] = String(activeTenant)
  }
  const url = path.startsWith('http')
    ? path
    : `/api/v1${path.startsWith('/') ? path : `/${path}`}`
  return fetch(url, { ...options, headers, credentials: 'same-origin' })
}
