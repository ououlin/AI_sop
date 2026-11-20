import { useCallback, useState } from 'react'

export interface AuthData {
  token: string
  role: string
  displayName: string
  permissions: string[]
}

/**
 * 登录态管理
 * - 从 localStorage 恢复登录信息
 * - 登录/登出同步持久化
 */
export function useAuth() {
  const [auth, setAuth] = useState<AuthData | null>(() => {
    const saved = localStorage.getItem('ai_sop_auth')
    if (!saved) return null
    try {
      const parsed = JSON.parse(saved) as AuthData
      return { ...parsed, permissions: parsed.permissions ?? [] }
    } catch {
      localStorage.removeItem('ai_sop_auth')
      return null
    }
  })

  const handleLogin = useCallback(
    (token: string, role: string, displayName: string, permissions: string[]) => {
      const authData = { token, role, displayName, permissions }
      localStorage.setItem('ai_sop_auth', JSON.stringify(authData))
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
    setAuth(null)
  }, [])

  return { auth, handleLogin, handleLogout }
}
