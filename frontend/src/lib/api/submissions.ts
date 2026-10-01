import { apiClient } from './client'
import type { Money } from './pricing'
import type { ListingAvailability } from './listings'

export type SubmissionStatus = 'pending' | 'accepted' | 'rejected'

export interface ProductSubmission {
  id: string
  status: SubmissionStatus
  proposedCode: string
  productCode: string | null
  name: string
  category: string
  subcategory: string | null
  description: string | null
  uom: string
  specifications: Record<string, string>
  askingPrice: Money
  minimumQuantity: string
  maximumQuantity: string | null
  availability: ListingAvailability
  supplierUserId: string
  supplierName: string
  organisation: string
  reviewNote: string | null
  createdAt: string
}

export interface SubmissionInput {
  proposedCode: string
  name: string
  category: string
  subcategory?: string | null
  description?: string | null
  uom: string
  specifications: Record<string, string>
  askingPrice: string
  currency: string
  minimumQuantity: string
  maximumQuantity?: string | null
  availability: ListingAvailability
}

export const SPEC_FIELDS = [
  ['grade', 'Grade'],
  ['mfi', 'MFI'],
  ['density', 'Density'],
  ['application', 'Application'],
  ['quality', 'Quality'],
] as const

export const listOwnSubmissions = (signal?: AbortSignal) =>
  apiClient.get<ProductSubmission[]>('/product-submissions', { signal })

export const submitProduct = (body: SubmissionInput) =>
  apiClient.post<ProductSubmission>('/product-submissions', body)

export const listAdminSubmissions = (signal?: AbortSignal) =>
  apiClient.get<ProductSubmission[]>('/admin/product-submissions', { signal, query: { status: 'pending' } })

export const acceptSubmission = (id: string, productCode: string) =>
  apiClient.post<ProductSubmission>(`/admin/product-submissions/${id}/accept`, { productCode })

export const rejectSubmission = (id: string, note: string) =>
  apiClient.post<ProductSubmission>(`/admin/product-submissions/${id}/reject`, { note })
