import { apiClient } from './client'
import type { Money } from './pricing'

export type ApprovalStatus = 'pending' | 'approved' | 'declined' | 'deal_rejected'

export interface OrderApproval {
  id: string
  status: ApprovalStatus
  negotiationId: string
  negotiationNumber: string
  productName: string
  amount: Money
  threshold: Money
  destinationPin: string
  freightBasis: 'standard' | 'distance'
  submittedBy: string
  decidedBy: string | null
  decisionNote: string | null
  createdAt: string
  decidedAt: string | null
}

export interface CompanyUser {
  id: string
  fullName: string
  email: string
  roles: string[]
  isActive: boolean
}

export interface Company {
  id: string
  name: string
  threshold: Money | null
  users: CompanyUser[] | null
}

export const listApprovals = (signal?: AbortSignal) =>
  apiClient.get<OrderApproval[]>('/order-approvals', { signal })

export const approveOrderRequest = (id: string) =>
  apiClient.post<OrderApproval>(`/order-approvals/${id}/approve`)

export const declineOrderRequest = (id: string, note?: string) =>
  apiClient.post<OrderApproval>(`/order-approvals/${id}/decline`, { note: note || null })

export const rejectDeal = (id: string, note?: string) =>
  apiClient.post<OrderApproval>(`/order-approvals/${id}/reject-deal`, { note: note || null })

export const getCompany = (signal?: AbortSignal) =>
  apiClient.get<Company>('/organisation', { signal })

export const setCompanyThreshold = (amount: string | null, currency: string | null) =>
  apiClient.put<Company>('/organisation/threshold', {
    amount: amount ? amount : null,
    currency: amount ? currency : null,
  })
