import { apiClient } from './client'
import type { Availability, BenchmarkSummary, CodeLabel } from './pricing'

/** Buyer catalogue product. Every price inside `pricing` is a SourceOne benchmark for one mapped series. */
export interface Product {
  productCode: string
  name: string
  category: string
  subcategory: string | null
  description: string | null
  uom: CodeLabel
  priceKind: 'sourceone_benchmark'
  priceLabel: 'SourceOne benchmark'
  availability: Availability
  listingCount: number
  defaultSeriesCode: string | null
  pricing: BenchmarkSummary[]
  specifications: { key: string; label: string; value: string | null }[]
}

export const listProducts = (query: { category?: string; q?: string } = {}, signal?: AbortSignal) =>
  apiClient.get<Product[]>('/products', { query, signal })

export const getProduct = (productCode: string, signal?: AbortSignal) =>
  apiClient.get<Product>(`/products/${encodeURIComponent(productCode)}`, { signal })

/** Pricing context for a market (and optionally currency); falls back to the product's default series. */
export function selectPricing(product: Product, context: { market?: string | null; currency?: string | null } = {}) {
  const match = product.pricing.find(
    (pricing) =>
      (!context.market || pricing.market.code === context.market) &&
      (!context.currency || pricing.currency === context.currency),
  )
  return match ?? product.pricing.find((pricing) => pricing.seriesCode === product.defaultSeriesCode) ?? null
}
