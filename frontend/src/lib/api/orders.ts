import { apiClient } from './client'
import type { Money } from './pricing'

export type OrderStatus = 'placed' | 'confirmed' | 'processing' | 'ready' | 'dispatched' | 'delivered' | 'cancelled'

export interface Order {
  id: string
  orderNumber: string
  status: OrderStatus
  product: { productCode: string; name: string; category: string }
  quantity: string
  uom: string
  currency: string
  /** Accepted negotiation price, frozen on the order; never a benchmark. */
  agreedPrice: { priceKind: 'negotiated_price'; unitPrice: Money; uom: string }
  totalValue: Money
  negotiation: { id: string; negotiationNumber: string; acceptedVersionNumber: number }
  buyer: { name: string; organisation: string }
  supplier: { name: string; organisation: string }
  viewerRole: 'buyer' | 'supplier'
  allowedActions: { cancel: boolean }
  createdAt: string
  updatedAt: string
  cancelledAt: string | null
  cancelReason: string | null
}

export interface TrackingStep {
  status: OrderStatus
  label: string
  state: 'completed' | 'current' | 'pending'
  at: string | null
  note: string | null
  changedBy: string | null
}

export interface OrderStatusEvent {
  fromStatus: OrderStatus | null
  toStatus: OrderStatus
  changedBy: string
  changedByRole: 'buyer' | 'supplier'
  note: string | null
  createdAt: string
}

export interface OrderTracking {
  orderId: string
  orderNumber: string
  status: OrderStatus
  product: Order['product']
  quantity: string
  uom: string
  buyer: Order['buyer']
  supplier: Order['supplier']
  viewerRole: 'buyer' | 'supplier'
  /** Only set for the assigned supplier while the order can still move forward. */
  nextStatus: OrderStatus | null
  canProgress: boolean
  steps: TrackingStep[]
  events: OrderStatusEvent[]
  lastUpdatedAt: string
}

const BASE = '/orders'

export const getOrderTracking = (id: string, signal?: AbortSignal) =>
  apiClient.get<OrderTracking>(`${BASE}/${id}/tracking`, { signal })

export const changeOrderStatus = (id: string, toStatus: OrderStatus, note?: string) =>
  apiClient.post<OrderTracking>(`${BASE}/${id}/status`, { toStatus, note: note || null })

export const listOrders = (signal?: AbortSignal) => apiClient.get<Order[]>(BASE, { signal })

export const getOrder = (id: string, signal?: AbortSignal) => apiClient.get<Order>(`${BASE}/${id}`, { signal })

export const createOrderFromNegotiation = (negotiationId: string) =>
  apiClient.post<Order>(`${BASE}/from-negotiation/${negotiationId}`)

export const cancelOrder = (id: string, reason?: string) => apiClient.post<Order>(`${BASE}/${id}/cancel`, { reason })
