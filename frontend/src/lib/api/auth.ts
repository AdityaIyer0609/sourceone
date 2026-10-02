import { apiClient } from './client'

export interface SessionUser {
  email: string
  fullName: string
  organisation: string
  roles: string[]
  hideSuppliers?: boolean
}

export interface Session {
  accessToken: string
  user: SessionUser
}

const STORAGE_KEY = 'sourceone.session'
const AUTH_EVENT = 'sourceone-auth'

export function readSession(): Session | null {
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  try {
    const session = JSON.parse(raw) as Session
    return session.accessToken && session.user?.email ? session : null
  } catch {
    return null
  }
}

export function saveSession(session: Session) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  window.dispatchEvent(new Event(AUTH_EVENT))
}

export function clearSession() {
  window.localStorage.removeItem(STORAGE_KEY)
  window.dispatchEvent(new Event(AUTH_EVENT))
}

export function onSessionChange(listener: () => void) {
  window.addEventListener(AUTH_EVENT, listener)
  return () => window.removeEventListener(AUTH_EVENT, listener)
}

export function authHeaders(): Record<string, string> {
  const session = readSession()
  return session ? { Authorization: `Bearer ${session.accessToken}` } : {}
}

export const login = (email: string, password: string) =>
  apiClient.post<{ accessToken: string; tokenType: string; expiresIn: number; user: SessionUser }>('/auth/login', { email, password })

export const currentUser = (signal?: AbortSignal) => apiClient.get<SessionUser>('/auth/me', { signal })
