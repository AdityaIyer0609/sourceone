import { apiClient } from './client'
import type { Money } from './pricing'

export type NegotiationStatus = 'draft' | 'open' | 'countered' | 'accepted' | 'rejected' | 'cancelled'
export type NegotiationParty = 'buyer' | 'supplier'

/** Benchmark = reference value, frozen when the negotiation started. */
export interface BenchmarkSnapshot {
  priceKind: 'sourceone_benchmark'
  label: string
  state: 'fresh' | 'stale' | 'rate_on_request'
  value: Money | null
  asOfDate: string | null
  seriesCode: string | null
  basis: string | null
}

/** Offer = proposed price. Versions are immutable and never overwritten. */
export interface NegotiationVersion {
  priceKind: 'offer'
  versionNumber: number
  offeredBy: NegotiationParty
  author: string
  offeredPrice: Money
  quantity: string
  uom: string
  message: string | null
  createdAt: string
}

export interface Negotiation {
  id: string
  negotiationNumber: string
  status: NegotiationStatus
  product: { productCode: string; name: string; category: string }
  quantity: string
  uom: string
  currency: string
  buyer: { name: string; organisation: string }
  supplier: { name: string; organisation: string }
  benchmark: BenchmarkSnapshot
  versions: NegotiationVersion[]
  /** Negotiated price = the accepted version's offer. */
  negotiated: { priceKind: 'negotiated_price'; versionNumber: number; price: Money; quantity: string; uom: string } | null
  awaiting: NegotiationParty | null
  viewerRole: NegotiationParty
  allowedActions: { offer: boolean; accept: boolean; reject: boolean; cancel: boolean }
  createdAt: string
  updatedAt: string
  closedAt: string | null
  closedReason: string | null
}

export interface OfferInput {
  offeredPrice: string
  quantity?: string
  message?: string
}

export interface StartNegotiationInput extends OfferInput {
  productCode: string
  seriesCode?: string
  quantity: string
  currency?: string
}

const BASE = '/negotiations'

export const listNegotiations = (signal?: AbortSignal) => apiClient.get<Negotiation[]>(BASE, { signal })

export const getNegotiation = (id: string, signal?: AbortSignal) => apiClient.get<Negotiation>(`${BASE}/${id}`, { signal })

export const startNegotiation = (input: StartNegotiationInput) => apiClient.post<Negotiation>(BASE, input)

export const submitOffer = (id: string, input: OfferInput) => apiClient.post<Negotiation>(`${BASE}/${id}/offers`, input)

export const acceptNegotiation = (id: string) => apiClient.post<Negotiation>(`${BASE}/${id}/accept`)

export const rejectNegotiation = (id: string, reason?: string) => apiClient.post<Negotiation>(`${BASE}/${id}/reject`, { reason })

export const cancelNegotiation = (id: string, reason?: string) => apiClient.post<Negotiation>(`${BASE}/${id}/cancel`, { reason })
