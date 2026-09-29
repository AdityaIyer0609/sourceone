import { authHeaders } from './auth'
import { ApiError, apiClient, getErrorMessage } from './client'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

export interface ProductDocument {
  id: string
  name: string
  documentType: string
  filename: string
  isActive: boolean
  createdAt: string
}

export interface ProductAnswer {
  id: string
  body: string
  supplierName: string
  organisation: string
  createdAt: string
}

export interface ProductQuestion {
  id: string
  body: string
  askedBy: string
  organisation: string
  status: 'open' | 'answered'
  createdAt: string
  answers: ProductAnswer[]
}

export interface QuestionList {
  canAsk: boolean
  canAnswer: boolean
  questions: ProductQuestion[]
}

export const listProductDocuments = (productCode: string, signal?: AbortSignal) =>
  apiClient.get<ProductDocument[]>(`/products/${encodeURIComponent(productCode)}/documents`, { signal })

export const listAdminDocuments = (productCode: string, signal?: AbortSignal) =>
  apiClient.get<ProductDocument[]>(`/admin/products/${encodeURIComponent(productCode)}/documents`, { signal })

export const uploadProductDocument = (productCode: string, fields: { name: string; documentType: string; file: File }) => {
  const body = new FormData()
  body.set('name', fields.name)
  body.set('documentType', fields.documentType)
  body.set('file', fields.file)
  return apiClient.post<ProductDocument>(`/admin/products/${encodeURIComponent(productCode)}/documents`, body)
}

export const setProductDocumentActive = (productCode: string, documentId: string, isActive: boolean) =>
  apiClient.post<ProductDocument>(`/admin/products/${encodeURIComponent(productCode)}/documents/${documentId}/active`, { isActive })

export const listProductQuestions = (productCode: string, signal?: AbortSignal) =>
  apiClient.get<QuestionList>(`/products/${encodeURIComponent(productCode)}/questions`, { signal })

export const askProductQuestion = (productCode: string, body: string) =>
  apiClient.post<ProductQuestion>(`/products/${encodeURIComponent(productCode)}/questions`, { body })

export const answerProductQuestion = (productCode: string, questionId: string, body: string) =>
  apiClient.post<ProductQuestion>(`/products/${encodeURIComponent(productCode)}/questions/${questionId}/answers`, { body })

export async function downloadProductDocument(productCode: string, documentId: string, filename: string) {
  const headers = new Headers(authHeaders())
  const response = await fetch(`${API_BASE_URL}/products/${encodeURIComponent(productCode)}/documents/${documentId}/file`, { headers })
  if (!response.ok) {
    let message = response.statusText
    try {
      message = getErrorMessage(await response.json())
    } catch {
      message = response.statusText
    }
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
