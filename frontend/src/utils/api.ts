/**
 * API 请求工具函数
 * 自动从 localStorage 读取 JWT Token 并设置 Authorization 头
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
  const url = path.startsWith('http')
    ? path
    : `/api/v1${path.startsWith('/') ? path : `/${path}`}`
  return fetch(url, { ...options, headers })
}
