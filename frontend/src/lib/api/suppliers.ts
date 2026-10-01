import { apiClient } from './client'
import type { Money } from './pricing'

export interface CountRate {
  available: boolean
  note: string
  count: number
  total: number
  percent: string | null
}

export interface SupplierProfile {
  organisationId: string
  name: string
  verificationStatus: 'unverified' | 'pending' | 'verified'
  dispatchPin: string | null
  dispatchLabel: string | null
  serviceRegions: { label: string; pinPrefix: string | null }[]
  people: { name: string; email: string | null }[]
  products: {
    productCode: string
    name: string
    uom: string
    minimumQuantity: string
    maximumQuantity: string | null
    askingPrice: Money
    availability: 'in_stock' | 'limited' | 'on_request'
  }[]
  responseTime: { available: boolean; note: string; sampleCount: number; averageHours: string | null }
  acceptance: CountRate
  orderCancellation: CountRate
  onTimeDelivery: CountRate
  quality: CountRate
  quoteCount: number
  orderCount: number
  quotes: { id: string; reference: string; productName: string; status: string; latestOffer: Money | null; updatedAt: string }[]
  orders: { id: string; reference: string; productName: string; status: string; totalValue: Money; updatedAt: string }[]
  canEditRegions: boolean
  canSetVerification: boolean
}

export const getSupplierProfile = (organisationId: string, signal?: AbortSignal) =>
  apiClient.get<SupplierProfile>(`/suppliers/${organisationId}`, { signal })

export const saveServiceRegions = (organisationId: string, regions: { label: string; pinPrefix: string | null }[]) =>
  apiClient.put<SupplierProfile>(`/suppliers/${organisationId}/service-regions`, { regions })

export const saveVerification = (organisationId: string, status: SupplierProfile['verificationStatus']) =>
  apiClient.patch<SupplierProfile>(`/suppliers/${organisationId}/verification`, { status })
