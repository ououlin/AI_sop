import { useCallback, useState } from 'react'

export interface AuthData {
  token: string
  role: string
  displayName: string
  permissions: string[]
  tenant: string
  tenantId: number
}

/**
 * 登录态管理
 * - 从 localStorage 恢复登录信息（老数据缺省补默认租户）
 * - 登录/登出同步持久化
 */
export function useAuth() {
  const [auth, setAuth] = useState<AuthData | null>(() => {
    const saved = localStorage.getItem('ai_sop_auth')
    if (!saved) return null
    try {
      const parsed = JSON.parse(saved) as Partial<AuthData>
      return {
        ...parsed,
        permissions: parsed.permissions ?? [],
        tenant: parsed.tenant ?? 'default',
        tenantId: parsed.tenantId ?? 1,
      } as AuthData
    } catch {
      localStorage.removeItem('ai_sop_auth')
      return null
    }
  })

  const handleLogin = useCallback(
    (
      token: string,
      role: string,
      displayName: string,
      permissions: string[],
      tenant: string,
      tenantId: number,
    ) => {
      const authData: AuthData = { token, role, displayName, permissions, tenant, tenantId }
      localStorage.setItem('ai_sop_auth', JSON.stringify(authData))
      localStorage.removeItem('ai_sop_active_tenant')
      setAuth(authData)
    },
    [],
  )

  const handleLogout = useCallback(() => {
    void fetch('/api/v1/auth/logout', {
      method: 'POST',
      credentials: 'same-origin',
    })
    localStorage.removeItem('ai_sop_auth')
    localStorage.removeItem('ai_sop_active_tenant')
    setAuth(null)
  }, [])

  return { auth, handleLogin, handleLogout }
}
