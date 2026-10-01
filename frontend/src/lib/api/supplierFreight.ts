import { apiClient } from './client'

export interface SupplierLane {
  id: string
  originPin: string
  destinationPin: string
  destinationLabel: string
  ratePerKg: string
  currency: string
  minimumFreight: string | null
  isActive: boolean
}

export interface SupplierKmRate {
  id: string
  currency: string
  ratePerKm: string
  minimumFreight: string | null
  isActive: boolean
}

export interface SupplierFreight {
  dispatchPin: string | null
  dispatchLabel: string | null
  lanes: SupplierLane[]
  kmRate: SupplierKmRate | null
}

export const readSupplierFreight = (signal?: AbortSignal) =>
  apiClient.get<SupplierFreight>('/supplier-freight', { signal })

export const saveDispatch = (body: { pin: string; label: string }) =>
  apiClient.put<SupplierFreight>('/supplier-freight/dispatch', body)

export const saveSupplierLane = (body: {
  destinationPin: string
  destinationLabel: string
  ratePerKg: string
  currency: string
  minimumFreight?: string | null
  isActive?: boolean
}) => apiClient.post<SupplierFreight>('/supplier-freight/lanes', body)

export const removeSupplierLane = (id: string) =>
  apiClient.delete<SupplierFreight>(`/supplier-freight/lanes/${id}`)

export const saveSupplierKmRate = (body: {
  ratePerKm: string
  currency: string
  minimumFreight?: string | null
  isActive?: boolean
}) => apiClient.put<SupplierFreight>('/supplier-freight/km-rate', body)
