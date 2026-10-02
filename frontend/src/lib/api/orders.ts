import { apiClient } from './client'
import type { OrderApproval } from './approvals'
import type { Money } from './pricing'

export type OrderStatus = 'placed' | 'confirmed' | 'processing' | 'ready' | 'dispatched' | 'in_transit' | 'delivered' | 'cancelled'

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
  charges: {
    material: Money
    freight: Money | null
    gstRatePercent: 18
    gstBasis: string
    gst: Money
    payable: Money
  }
  destinationPin: string | null
  freightStatus: 'estimated' | 'on_request' | null
  freight: Money | null
  freightMatch: 'lane' | 'zone' | 'default' | 'distance' | null
  negotiation: { id: string; negotiationNumber: string; acceptedVersionNumber: number }
  buyer: { name: string; organisation: string; organisationId: string }
  supplier: { name: string; organisation: string; organisationId: string }
  viewerRole: 'buyer' | 'supplier'
  allowedActions: { cancel: boolean }
  createdAt: string
  updatedAt: string
  cancelledAt: string | null
  cancelReason: string | null
  requirements: { key: string; label: string; value: string }[]
  documents: { id: string; documentType: string; filename: string; status: 'submitted' | 'accepted' | 'rejected'; byteSize: number }[]
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

export interface ShipmentDetails {
  lrNumber: string | null
  transporter: string | null
  vehicle: string | null
  eta: string | null
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
  shipment: ShipmentDetails
  requiredBy: string | null
  delayed: boolean
  pod: { id: string; filename: string; status: 'submitted' | 'accepted' | 'rejected' } | null
}

const BASE = '/orders'

export const getOrderTracking = (id: string, signal?: AbortSignal) =>
  apiClient.get<OrderTracking>(`${BASE}/${id}/tracking`, { signal })

export const changeOrderStatus = (id: string, toStatus: OrderStatus, note?: string, shipment?: ShipmentDetails) =>
  apiClient.post<OrderTracking>(`${BASE}/${id}/status`, { toStatus, note: note || null, ...shipment })

export const saveShipment = (id: string, shipment: ShipmentDetails) =>
  apiClient.post<OrderTracking>(`${BASE}/${id}/shipment`, shipment)

export const listOrders = (signal?: AbortSignal) => apiClient.get<Order[]>(BASE, { signal })

export const getOrder = (id: string, signal?: AbortSignal) => apiClient.get<Order>(`${BASE}/${id}`, { signal })

export const placeAtAsking = (body: {
  productCode: string
  supplierUserId: string
  quantity: string
  destinationPin: string
  freightBasis?: 'standard' | 'distance'
  paymentTerms?: string
}) => apiClient.post<Order | OrderApproval>(`${BASE}/from-listing`, body)

export const createOrderFromNegotiation = (
  negotiationId: string,
  body: { destinationPin: string; freightBasis: 'standard' | 'distance' },
) => apiClient.post<Order | OrderApproval>(`${BASE}/from-negotiation/${negotiationId}`, body)

export function isPlacedOrder(result: Order | OrderApproval): result is Order {
  return 'orderNumber' in result
}

export const cancelOrder = (id: string, reason?: string) => apiClient.post<Order>(`${BASE}/${id}/cancel`, { reason })

export const ORDER_DOCUMENT_TYPES = [
  ['coa', 'COA'],
  ['mtc', 'MTC'],
  ['test_certificate', 'Test certificate'],
  ['inspection_report', 'Inspection report'],
  ['invoice', 'Invoice'],
  ['lr', 'LR'],
  ['eway_bill', 'E-way bill'],
  ['packing_list', 'Packing list'],
  ['pod', 'POD'],
] as const

export const uploadOrderDocument = (orderId: string, documentType: string, file: File) => {
  const body = new FormData()
  body.set('documentType', documentType)
  body.set('file', file)
  return apiClient.post<Order['documents'][number]>(`${BASE}/${orderId}/documents`, body)
}

export const reviewOrderDocument = (orderId: string, documentId: string, status: 'accepted' | 'rejected') =>
  apiClient.post<Order['documents'][number]>(`${BASE}/${orderId}/documents/${documentId}/review`, { status })

export async function downloadOrderDocument(orderId: string, documentId: string, filename: string) {
  const { authHeaders } = await import('./auth')
  const { ApiError, getErrorMessage } = await import('./client')
  const headers = new Headers(authHeaders())
  const response = await fetch(`${(import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')}/orders/${orderId}/documents/${documentId}/file`, { headers })
  if (!response.ok) {
    let message = response.statusText
    try { message = getErrorMessage(await response.json()) } catch { message = response.statusText }
    throw new ApiError(response.status, message || 'Download failed', null)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export type ReorderBlock = 'cancelled' | 'inactive_product' | 'inactive_supplier' | 'no_listing'

export interface ReorderItem {
  orderId: string
  orderNumber: string
  orderStatus: OrderStatus
  productCode: string
  productName: string
  supplierUserId: string
  supplierName: string
  organisation: string
  organisationId: string
  quantity: string
  uom: string
  currency: string
  previousPrice: Money
  orderedAt: string
  available: boolean
  unavailableReason: ReorderBlock | null
  currentAskingPrice: Money | null
  currentBenchmark: Money | null
}

export interface ReorderResult {
  negotiationId: string
  negotiationNumber: string
  quantity: string
  uom: string
  offeredPrice: Money
  previousPrice: Money
  currentBenchmark: Money | null
  destinationPin: string | null
  freightStatus: 'estimated' | 'on_request' | 'not_requested'
  freight: Money | null
  note: string
}

export const listReorders = (signal?: AbortSignal) => apiClient.get<ReorderItem[]>(`${BASE}/reorder`, { signal })

export const startReorder = (orderId: string, body: { quantity: string; destinationPin?: string }) =>
  apiClient.post<ReorderResult>(`${BASE}/${orderId}/reorder`, body)
