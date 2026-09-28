import { apiClient } from './client'

export interface HealthResponse {
  status: 'ok' | 'degraded'
  database: 'ok' | 'unavailable'
}

export function getHealth(signal?: AbortSignal) {
  return apiClient.get<HealthResponse>('/health', { signal })
}
