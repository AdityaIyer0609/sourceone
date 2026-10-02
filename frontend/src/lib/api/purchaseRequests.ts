import { apiClient } from './client'
import { notifyNegotiationsChanged } from './negotiations'
import type { Money, QuotePosition } from './pricing'

export type RequestStatus = 'draft' | 'sent' | 'in_negotiation' | 'converted' | 'cancelled'

export interface RequestSupplier {
  supplierUserId: string
  supplierName: string
  organisation: string
  organisationId: string
  negotiationId: string | null
  negotiationNumber: string | null
  negotiationStatus: string | null
  askingPrice: Money | null
  latestOffer: Money | null
  materialValue: Money | null
  freightStatus: 'estimated' | 'on_request'
  freight: Money | null
  landedEstimate: Money | null
  charges: {
    material: Money
    freight: Money | null
    gstRatePercent: 18
    gstBasis: string
    gst: Money
    payable: Money
  } | null
  quote: QuotePosition
  requirementResponses: { key: string; status: 'met' | 'not_met'; comment: string | null }[]
  supplyNote: string | null
  availability: 'in_stock' | 'limited' | 'on_request' | null
  minimumQuantity: string | null
  maximumQuantity: string | null
  soldOut: boolean
}

export interface PurchaseRequest {
  id: string
  requestNumber: string
  status: RequestStatus
  productCode: string
  productName: string
  quantity: string
  uom: string
  destinationPin: string
  freightBasis: 'standard' | 'distance'
  requiredBy: string | null
  paymentTerms: string | null
  requirements: { key: string; label: string; value: string }[] | null
  message: string | null
  offeredPrice: string | null
  buyerName: string
  buyerOrganisation: string
  viewerRole: 'buyer' | 'supplier'
  suppliers: RequestSupplier[]
  canEditSuppliers: boolean
  canSend: boolean
  canCancel: boolean
  createdAt: string
}

export interface PurchaseRequestInput {
  productCode: string
  quantity: string
  uom: string
  destinationPin: string
  freightBasis?: 'standard' | 'distance'
  requiredBy?: string
  paymentTerms?: string
  message?: string
  offeredPrice?: string
  supplierUserIds?: string[]
}

export const listPurchaseRequests = (signal?: AbortSignal) =>
  apiClient.get<PurchaseRequest[]>('/purchase-requests', { signal })

export const createPurchaseRequest = (body: PurchaseRequestInput) =>
  apiClient.post<PurchaseRequest>('/purchase-requests', body)

export const setRequestSuppliers = (id: string, supplierUserIds: string[]) =>
  apiClient.put<PurchaseRequest>(`/purchase-requests/${id}/suppliers`, { supplierUserIds })

function changed<T>(pending: Promise<T>) {
  return pending.then((result) => {
    notifyNegotiationsChanged()
    return result
  })
}

export const sendPurchaseRequest = (id: string) =>
  changed(apiClient.post<PurchaseRequest>(`/purchase-requests/${id}/send`))

export const cancelPurchaseRequest = (id: string) =>
  changed(apiClient.post<PurchaseRequest>(`/purchase-requests/${id}/cancel`))

export const cancelRequestSupplier = (id: string, supplierUserId: string) =>
  changed(apiClient.post<PurchaseRequest>(`/purchase-requests/${id}/suppliers/${supplierUserId}/cancel`))

export const sendRequestSupplier = (id: string, supplierUserId: string, offeredPrice?: string) =>
  changed(apiClient.post<PurchaseRequest>(`/purchase-requests/${id}/suppliers/${supplierUserId}/send`, {
    offeredPrice: offeredPrice || undefined,
  }))

export const placeRequestSupplier = (id: string, supplierUserId: string) =>
  changed(apiClient.post<PurchaseRequest>(`/purchase-requests/${id}/suppliers/${supplierUserId}/order`))
