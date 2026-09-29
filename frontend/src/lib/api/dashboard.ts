import { apiClient } from './client'
import type { Money } from './pricing'

export interface DashboardActivity {
  kind: 'order' | 'negotiation'
  id: string
  reference: string
  productName: string
  counterparty: string
  quantity: string
  uom: string
  value: Money | null
  valueKind: 'order_total' | 'offer'
  status: string
  updatedAt: string
  canReorder: boolean
}

export interface BuyerDashboard {
  activeOrders: number
  openNegotiations: number
  pendingActions: number
  spend: { currency: string; amount: string }[]
  ordersByStatus: Record<string, number>
  recentOrders: DashboardActivity[]
  recentNegotiations: DashboardActivity[]
}

export const getDashboard = (signal?: AbortSignal) => apiClient.get<BuyerDashboard>('/dashboard', { signal })
