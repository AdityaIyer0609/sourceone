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

export interface DashboardMetric {
  available: boolean
  note: string
  percent: string | null
  averageHours: string | null
}

export interface BuyerDashboard {
  activeOrders: number
  openNegotiations: number
  openRequests: number
  pendingActions: number
  spendBasis: 'material'
  spend: { currency: string; amount: string }[]
  spendByProduct: { label: string; currency: string; amount: string; orderCount: number }[]
  spendBySupplier: { label: string; currency: string; amount: string; orderCount: number }[]
  variance: {
    orderId: string
    orderNumber: string
    productName: string
    agreedUnitPrice: Money
    snapshot: Money
    unitDifference: Money
    materialDifference: Money
  }[]
  delivery: { available: boolean; note: string; onTime: number; delivered: number; percent: string | null }
  suppliers: {
    organisationId: string
    organisation: string
    acceptance: DashboardMetric
    orderCancellation: DashboardMetric
    quality: DashboardMetric
    responseTime: DashboardMetric
  }[]
  alerts: { kind: 'negotiation' | 'approval' | 'order'; id: string; title: string; detail: string }[]
  ordersByStatus: Record<string, number>
  recentOrders: DashboardActivity[]
  recentNegotiations: DashboardActivity[]
}

export const getDashboard = (signal?: AbortSignal) => apiClient.get<BuyerDashboard>('/dashboard', { signal })

export interface SupplierDashboard {
  openRequests: number
  openNegotiations: number
  ordersToConfirm: number
  listingsToReview: number
  requests: { id: string; title: string; detail: string }[]
  negotiations: { id: string; title: string; detail: string }[]
  orders: { id: string; title: string; detail: string }[]
  listings: {
    id: string
    productCode: string
    productName: string
    availability: string
    isActive: boolean
    askingPrice: Money
  }[]
  documents: {
    id: string
    orderId: string
    orderNumber: string
    documentType: string
    filename: string
    status: 'submitted' | 'accepted' | 'rejected'
  }[]
  performance: {
    acceptance: DashboardMetric & { count: number; total: number }
    orderCancellation: DashboardMetric & { count: number; total: number }
    onTimeDelivery: DashboardMetric & { count: number; total: number }
    quality: DashboardMetric & { count: number; total: number }
    responseTime: { available: boolean; note: string; sampleCount: number; averageHours: string | null }
  }
  alerts: BuyerDashboard['alerts']
}

export const getSupplierDashboard = (signal?: AbortSignal) =>
  apiClient.get<SupplierDashboard>('/supplier-dashboard', { signal })
