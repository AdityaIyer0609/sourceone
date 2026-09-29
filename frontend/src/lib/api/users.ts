import { apiClient } from './client'

export const USER_ROLES = ['platform_admin', 'pricing_admin', 'buyer', 'supplier'] as const
export type UserRole = (typeof USER_ROLES)[number]

export interface AdminUser {
  id: string
  fullName: string
  email: string
  organisation: string
  roles: string[]
  isActive: boolean
  isSystem: boolean
}

export const listAdminUsers = (signal?: AbortSignal) =>
  apiClient.get<AdminUser[]>('/admin/users', { signal })

export const createAdminUser = (body: { fullName: string; email: string; password: string; role: string }) =>
  apiClient.post<AdminUser>('/admin/users', body)

export const setAdminUserActive = (id: string, isActive: boolean) =>
  apiClient.post<AdminUser>(`/admin/users/${id}/active`, { isActive })

export const setAdminUserRole = (id: string, role: string) =>
  apiClient.post<AdminUser>(`/admin/users/${id}/role`, { role })
