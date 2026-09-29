import { authHeaders, clearSession } from './auth'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

type QueryValue = string | number | boolean | null | undefined

export interface RequestOptions extends Omit<RequestInit, 'method' | 'body'> {
  query?: Record<string, QueryValue>
  body?: unknown
}

export class ApiError extends Error {
  readonly status: number
  readonly data: unknown
  /** Domain error code, e.g. FOUR_EYES_REQUIRED, when the backend provides one. */
  readonly code?: string

  constructor(status: number, message: string, data: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
    this.code = extractErrorCode(data)
  }
}

interface DomainErrorBody {
  error: { code?: unknown; message?: unknown }
}

function isDomainError(data: unknown): data is DomainErrorBody {
  return !!data && typeof data === 'object' && 'error' in data && !!(data as DomainErrorBody).error && typeof (data as DomainErrorBody).error === 'object'
}

function extractErrorCode(data: unknown): string | undefined {
  return isDomainError(data) && typeof data.error.code === 'string' ? data.error.code : undefined
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
  if (!query) return url

  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) params.append(key, String(value))
  }
  const search = params.toString()
  return search ? `${url}?${search}` : url
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined
  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) return response.json()
  const text = await response.text()
  return text || undefined
}

// Domain errors are { error: { code, message, details } }; FastAPI's own errors are
// { detail: string } or { detail: [{ msg: string }, ...] }.
function extractErrorMessage(data: unknown): string | undefined {
  if (typeof data === 'string') return data
  if (isDomainError(data) && typeof data.error.message === 'string') return data.error.message
  if (!data || typeof data !== 'object' || !('detail' in data)) return undefined
  const { detail } = data as { detail: unknown }
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item === 'object' && 'msg' in item ? String(item.msg) : undefined))
      .filter(Boolean)
    if (messages.length) return messages.join(', ')
  }
  return undefined
}

async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const { query, body, headers, ...init } = options
  const requestHeaders = new Headers(headers)
  if (!requestHeaders.has('Accept')) requestHeaders.set('Accept', 'application/json')
  for (const [name, value] of Object.entries(authHeaders())) {
    if (!requestHeaders.has(name)) requestHeaders.set(name, value)
  }
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData
  if (body !== undefined && !isForm && !requestHeaders.has('Content-Type')) {
    requestHeaders.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      ...init,
      method,
      headers: requestHeaders,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'Unable to reach the server. Check your connection and try again.', error)
  }

  const data = await parseBody(response)
  if (!response.ok) {
    if (response.status === 401 && !path.endsWith('/auth/login')) clearSession()
    const message = extractErrorMessage(data) || response.statusText || `Request failed with status ${response.status}`
    throw new ApiError(response.status, message, data)
  }
  return data as T
}

export const apiClient = {
  get: <T>(path: string, options?: RequestOptions) => request<T>('GET', path, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>('POST', path, { ...options, body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>('PUT', path, { ...options, body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>('PATCH', path, { ...options, body }),
  delete: <T>(path: string, options?: RequestOptions) => request<T>('DELETE', path, options),
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'An unexpected error occurred.'
}

export function getErrorTitle(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Something went wrong'
  if (error.status === 0) return 'Server unreachable'
  if (error.status === 401) return 'Sign-in required'
  if (error.status === 403) return 'Permission denied'
  if (error.status === 404) return 'Not found'
  if (error.status === 409 || error.status === 422) return 'Request not accepted'
  return 'Something went wrong'
}
