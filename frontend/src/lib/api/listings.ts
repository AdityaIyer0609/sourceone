import { apiClient } from './client'
import type { Money } from './pricing'

export type ListingAvailability = 'in_stock' | 'limited' | 'on_request'

export interface SupplierListing {
  id: string
  productCode: string
  supplierUserId: string
  supplierName: string
  organisation: string
  originPin: string | null
  originLabel: string | null
  uom: string
  minimumQuantity: string
  askingPrice: Money
  availability: ListingAvailability
  isActive: boolean
}

export const listProductListings = (productCode: string, currency?: string, signal?: AbortSignal) =>
  apiClient.get<SupplierListing[]>(`/products/${encodeURIComponent(productCode)}/listings`, {
    query: currency ? { currency } : undefined,
    signal,
  })
