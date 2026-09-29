import { apiClient } from './client'

export interface ProductSeries {
  seriesCode: string
  displayName: string
  currency: string
  displayOrder: number
  isActive: boolean
  availability: 'available' | 'rate_on_request'
}

export interface AdminProduct {
  productCode: string
  name: string
  category: string
  subcategory: string | null
  description: string | null
  uom: string
  isActive: boolean
  benchmarkStatus: 'available' | 'rate_on_request'
  listingCount: number
  series: ProductSeries[]
  specifications: { key: string; label: string; value: string | null }[]
}

export interface ProductInput {
  productCode: string
  name: string
  category: string
  subcategory?: string | null
  description?: string | null
  uom: string
  isActive: boolean
  specifications?: Record<string, string | null>
}

export interface ProductEdit {
  name: string
  category: string
  subcategory?: string | null
  description?: string | null
  specifications?: Record<string, string | null>
}

const BASE = '/admin/products'

export const listAdminProducts = (signal?: AbortSignal) => apiClient.get<AdminProduct[]>(BASE, { signal })

export const createAdminProduct = (body: ProductInput) => apiClient.post<AdminProduct>(BASE, body)

export const updateAdminProduct = (code: string, body: ProductEdit) =>
  apiClient.patch<AdminProduct>(`${BASE}/${encodeURIComponent(code)}`, body)

export const setAdminProductActive = (code: string, isActive: boolean) =>
  apiClient.post<AdminProduct>(`${BASE}/${encodeURIComponent(code)}/active`, { isActive })

export const mapProductSeries = (code: string, seriesCode: string) =>
  apiClient.post<AdminProduct>(`${BASE}/${encodeURIComponent(code)}/series`, { seriesCode, displayOrder: 0 })

export const setProductSeriesActive = (code: string, seriesCode: string, isActive: boolean) =>
  apiClient.post<AdminProduct>(`${BASE}/${encodeURIComponent(code)}/series/${encodeURIComponent(seriesCode)}/active`, { isActive })
