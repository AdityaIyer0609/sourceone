import { apiClient } from './client'
import type { Money } from './pricing'

export type ListingAvailability = 'in_stock' | 'limited' | 'on_request'

export interface SupplierListing {
  id: string
  productCode: string
  productName: string
  supplierUserId: string
  supplierName: string
  organisation: string
  organisationId: string
  originPin: string | null
  originLabel: string | null
  uom: string
  minimumQuantity: string
  maximumQuantity: string | null
  askingPrice: Money
  availability: ListingAvailability
  isActive: boolean
}

export const listOwnListings = (signal?: AbortSignal) => apiClient.get<SupplierListing[]>('/listings', { signal })

export const updateListing = (
  id: string,
  body: { askingPrice?: string; minimumQuantity?: string; maximumQuantity?: string | null; availability?: ListingAvailability; isActive?: boolean },
) => apiClient.patch<SupplierListing>(`/listings/${id}`, body)

export const createListing = (body: {
  productCode: string
  minimumQuantity: string
  maximumQuantity?: string | null
  askingPrice: string
  currency: string
  availability: ListingAvailability
  isActive?: boolean
}) => apiClient.post<SupplierListing>('/listings', body)

export const listProductListings = (productCode: string, currency?: string, signal?: AbortSignal) =>
  apiClient.get<SupplierListing[]>(`/products/${encodeURIComponent(productCode)}/listings`, {
    query: currency ? { currency } : undefined,
    signal,
  })

export interface SupplierMatch {
  supplierUserId: string
  supplierName: string
  organisation: string
  organisationId: string
  askingPrice: Money
  minimumQuantity: string
  maximumQuantity: string | null
  uom: string
  availability: ListingAvailability
  originPin: string | null
  originLabel: string | null
  meetsMinimum: boolean
  freightStatus: 'estimated' | 'on_request'
  freight: Money | null
  freightMatch: 'lane' | 'zone' | 'default' | null
  reasons: string[]
  comparison: {
    basis: 'lane' | 'per_km' | null
    freight: Money | null
    material: Money
    landed: Money | null
    factor: string | null
    adjusted: Money | null
    notes: string[]
    place: number | null
  }
}

export interface SupplierMatchList {
  productCode: string
  quantity: string
  uom: string
  destinationPin: string
  matches: SupplierMatch[]
}

export const listSupplierMatches = (
  productCode: string,
  query: { quantity: string; uom: string; destinationPin: string; currency?: string },
  signal?: AbortSignal,
) => apiClient.get<SupplierMatchList>(`/products/${encodeURIComponent(productCode)}/supplier-matches`, { query, signal })
