import { apiClient } from './client'
import type { Money } from './pricing'

export interface FreightRule {
  id: string
  originPin: string
  originLabel: string
  destinationPin: string
  destinationLabel: string
  ratePerKg: string
  rateUnit: 'KG'
  currency: string
  minimumFreight: string | null
  isActive: boolean
  effectiveFrom: string
  effectiveTo: string | null
}

export interface FreightRuleInput {
  originPin: string
  originLabel: string
  destinationPin: string
  destinationLabel: string
  ratePerKg: string
  currency: string
  minimumFreight?: string | null
  isActive: boolean
  effectiveFrom: string
  effectiveTo?: string | null
}

export interface FreightEstimate {
  supplierUserId: string
  productCode: string
  quantity: string
  uom: string
  originPin: string | null
  originLabel: string | null
  destinationPin: string
  destinationLabel: string | null
  supplierAskingPrice: Money
  materialValue: Money
  freightStatus: 'estimated' | 'on_request'
  freight: Money | null
  minimumFreightApplied: boolean
  landedCostPerUnit: Money | null
  landedValue: Money | null
  ruleId: string | null
  note: string
}

export const listFreightRules = (signal?: AbortSignal) =>
  apiClient.get<FreightRule[]>('/admin/freight/rules', { signal })

export const createFreightRule = (body: FreightRuleInput) =>
  apiClient.post<FreightRule>('/admin/freight/rules', body)

export const updateFreightRule = (id: string, body: FreightRuleInput) =>
  apiClient.patch<FreightRule>(`/admin/freight/rules/${id}`, body)

export const estimateFreight = (body: {
  supplierUserId: string
  productCode: string
  quantity: string
  destinationPin: string
}, signal?: AbortSignal) => apiClient.post<FreightEstimate>('/freight/estimates', body, { signal })
