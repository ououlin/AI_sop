import { useCallback, useState } from 'react'

export interface AuthData {
  token: string
  role: string
  displayName: string
}

/**
 * 登录态管理
 * - 从 localStorage 恢复登录信息
 * - 登录/登出同步持久化
 */
export function useAuth() {
  const [auth, setAuth] = useState<AuthData | null>(() => {
    const saved = localStorage.getItem('ai_sop_auth')
    return saved ? JSON.parse(saved) : null
  })

  const handleLogin = useCallback(
    (token: string, role: string, displayName: string) => {
      const authData = { token, role, displayName }
      localStorage.setItem('ai_sop_auth', JSON.stringify(authData))
      setAuth(authData)
    },
    [],
  )

  const handleLogout = useCallback(() => {
    localStorage.removeItem('ai_sop_auth')
    setAuth(null)
  }, [])

  return { auth, handleLogin, handleLogout }
}
