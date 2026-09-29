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
  match: 'lane' | 'zone' | 'default' | 'distance' | null
  roadDistanceKm: string | null
  distanceSource: 'geoapify' | 'cache' | null
  distanceStatus: 'estimated' | 'on_request' | 'not_requested'
  distanceFreight: Money | null
  distanceMinimumApplied: boolean
  distanceLandedPerUnit: Money | null
  distanceLandedValue: Money | null
  distanceRatePerKm: string | null
  distanceNote: string | null
  note: string
}

export type FreightBasis = 'standard' | 'distance'

export function shownFreight(estimate: FreightEstimate, basis: FreightBasis) {
  if (basis === 'distance') {
    const source = estimate.distanceSource === 'cache' ? 'cached' : 'Geoapify'
    return {
      status: estimate.distanceStatus,
      freight: estimate.distanceFreight,
      perUnit: estimate.distanceLandedPerUnit,
      landed: estimate.distanceLandedValue,
      note: estimate.distanceNote ?? estimate.note,
      label: estimate.roadDistanceKm ? `Estimated road distance · ${estimate.roadDistanceKm} km · ${source}` : 'Estimated road distance',
      rate: estimate.distanceRatePerKm,
    }
  }
  const label = estimate.match === 'lane' || estimate.match === 'zone'
    ? 'Saved freight'
    : estimate.match === 'default'
      ? 'Default rate'
      : estimate.destinationLabel
  return {
    status: estimate.freightStatus,
    freight: estimate.freight,
    perUnit: estimate.landedCostPerUnit,
    landed: estimate.landedValue,
    note: estimate.note,
    label,
    rate: null as string | null,
  }
}

export interface FreightDefault {
  id: string
  currency: string
  ratePerKg: string
  minimumFreight: string | null
  isActive: boolean
}

export const listFreightRules = (signal?: AbortSignal) =>
  apiClient.get<FreightRule[]>('/admin/freight/rules', { signal })

export const createFreightRule = (body: FreightRuleInput) =>
  apiClient.post<FreightRule>('/admin/freight/rules', body)

export const updateFreightRule = (id: string, body: FreightRuleInput) =>
  apiClient.patch<FreightRule>(`/admin/freight/rules/${id}`, body)

export const listFreightDefaults = (signal?: AbortSignal) =>
  apiClient.get<FreightDefault[]>('/admin/freight/defaults', { signal })

export const saveFreightDefault = (body: { currency: string; ratePerKg: string; minimumFreight?: string | null; isActive: boolean }) =>
  apiClient.put<FreightDefault>('/admin/freight/defaults', body)

export interface FreightDistanceRate {
  id: string
  currency: string
  ratePerKm: string
  minimumFreight: string | null
  isActive: boolean
}

export const listFreightDistanceRates = (signal?: AbortSignal) =>
  apiClient.get<FreightDistanceRate[]>('/admin/freight/distance-rates', { signal })

export const saveFreightDistanceRate = (body: { currency: string; ratePerKm: string; minimumFreight?: string | null; isActive: boolean }) =>
  apiClient.put<FreightDistanceRate>('/admin/freight/distance-rates', body)

export const estimateFreight = (body: {
  supplierUserId: string
  productCode: string
  quantity: string
  destinationPin: string
  includeDistance?: boolean
}, signal?: AbortSignal) => apiClient.post<FreightEstimate>('/freight/estimates', { includeDistance: true, ...body }, { signal })
