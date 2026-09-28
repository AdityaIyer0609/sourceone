import { apiClient } from './client'

// --- Shared ----------------------------------------------------------------------------------

export interface Money {
  amount: string
  currency: string
}

export interface CodeLabel {
  code: string
  label: string
}

export type Availability = 'available' | 'rate_on_request'
export type FreshnessState = 'fresh' | 'stale'
export type DataState = 'ok' | 'insufficient_data'
export type HistoryRange = '1D' | '7D' | '1M' | '3M' | '1Y'

export interface HistoryPoint {
  at: string
  value: string
  benchmarkId: string
}

// --- Buyer contracts (no producer or source information) --------------------------------------

export interface BenchmarkSummary {
  seriesCode: string
  name: string
  category: string
  grade: CodeLabel
  market: CodeLabel
  priceBasis: CodeLabel
  taxBasis: CodeLabel
  unit: CodeLabel
  currency: string
  priceKind: 'sourceone_benchmark'
  priceLabel: 'SourceOne benchmark'
  availability: Availability
  unavailableReason: string | null
  current: {
    benchmarkId: string
    value: Money
    effectiveFrom: string
    publishedAt: string
    freshness: { state: FreshnessState; asOfDate: string; staleAfter: string }
  } | null
  movement: {
    state: DataState
    previousValue: Money | null
    previousAsOfDate: string | null
    absolute: Money | null
    percent: string | null
  }
  sparkline: { range: string; state: DataState; points: HistoryPoint[] }
}

export interface BenchmarkHistory {
  seriesCode: string
  range: HistoryRange
  currency: string
  unit: string
  state: DataState
  carryIn: HistoryPoint | null
  points: HistoryPoint[]
  gaps: { start: string; end: string; reason: string }[]
  stats: {
    state: DataState
    pointCount: number
    high: string | null
    low: string | null
    average: string | null
    volatility: { state: DataState; level: 'low' | 'medium' | 'high' | null }
  }
}

export interface MaterialEstimate {
  priceKind: 'estimated_material_value'
  label: string
  informational: boolean
  seriesCode: string
  availability: Availability
  quantity: string
  unit: string
  unitValue: Money | null
  amount: Money | null
  benchmarkId: string | null
  freshnessState: FreshnessState | null
}

export const listBenchmarks = (query: { category?: string; market?: string; currency?: string } = {}, signal?: AbortSignal) =>
  apiClient.get<BenchmarkSummary[]>('/benchmarks', { query, signal })

export const getBenchmark = (seriesCode: string, signal?: AbortSignal) =>
  apiClient.get<BenchmarkSummary>(`/benchmarks/${encodeURIComponent(seriesCode)}`, { signal })

export const getBenchmarkHistory = (seriesCode: string, range: HistoryRange, signal?: AbortSignal) =>
  apiClient.get<BenchmarkHistory>(`/benchmarks/${encodeURIComponent(seriesCode)}/history`, { query: { range }, signal })

export const getMaterialEstimate = (seriesCode: string, quantity: number, unit = 'KG', signal?: AbortSignal) =>
  apiClient.get<MaterialEstimate>(`/benchmarks/${encodeURIComponent(seriesCode)}/estimate`, { query: { quantity, unit }, signal })

// --- Admin contracts ---------------------------------------------------------------------------

export interface Ref {
  id: string
  code: string
  name: string
}

export interface RateSource {
  id: string
  code: string
  name: string
  sourceType: string
  isActive: boolean
  priority: number
  stalenessDays: number
  publishingPolicy: string
  profileVersion: number
}

export interface SourceRate {
  id: string
  sourceCode: string
  importBatchId: string | null
  sourceRowRef: string
  sourceAsOfDate: string
  producer: Ref | null
  rawProducer: string | null
  rawGrade: string | null
  rawLocation: string | null
  originLocation: string | null
  rawSector: string | null
  sector: string | null
  application: string | null
  grade: Ref | null
  market: Ref | null
  seriesCode: string | null
  value: Money | null
  unit: string | null
  priceBasis: string | null
  taxBasis: string | null
  resolutionStatus: 'resolved' | 'unresolved' | 'ignored'
  resolutionReason: string | null
  isBenchmarkEligible: boolean
  eligibilityReason: string | null
  isUnchanged: boolean
  normalizationProfileVersion: number
  createdAt: string
}

export interface RateSeries {
  id: string
  code: string
  displayName: string
  grade: Ref
  market: Ref
  priceBasis: CodeLabel
  taxBasis: CodeLabel
  currency: string
  unit: CodeLabel
  isActive: boolean
  availability: Availability
  freshnessState: FreshnessState | null
  currentBenchmarkId: string | null
}

export type BenchmarkStatus = 'draft' | 'submitted' | 'published' | 'rejected' | 'withdrawn'

export interface BenchmarkAdmin {
  id: string
  seriesId: string
  seriesCode: string
  status: BenchmarkStatus
  value: Money
  unit: string
  priceBasis: string
  taxBasis: string
  method: 'adopted' | 'manual' | 'aggregated'
  origin: 'system_suggestion' | 'human'
  isEdited: boolean
  fourEyesRequired: boolean
  primarySourceCode: string
  inputs: { sourceRateId: string; role: string; sourceRowRef: string; rawProducer: string | null; sourceAsOfDate: string }[]
  sourceAsOfDate: string
  effectiveFrom: string
  effectiveUntil: string | null
  stalenessDays: number | null
  staleAfter: string | null
  reason: string | null
  evidenceRef: string | null
  createdBy: string | null
  createdAt: string
  lastEditedBy: string | null
  lastEditedAt: string | null
  submittedBy: string | null
  submittedAt: string | null
  publishedBy: string | null
  publishedAt: string | null
  rejectedBy: string | null
  rejectedAt: string | null
  rejectedReason: string | null
  withdrawnBy: string | null
  withdrawnAt: string | null
  withdrawnReason: string | null
  rowVersion: number
}

export interface SeriesTimeline {
  series: RateSeries
  benchmarks: BenchmarkAdmin[]
}

export interface AuditEvent {
  id: string
  entityType: string
  entityId: string
  action: string
  actor: string | null
  occurredAt: string
  fromStatus: string | null
  toStatus: string | null
  reason: string | null
  changes: Record<string, unknown> | null
}

export type CreateBenchmarkInput =
  | { mode: 'select_source_rate'; sourceRateId: string; seriesId?: string; effectiveFrom?: string; effectiveUntil?: string }
  | {
      mode: 'manual'
      seriesId: string
      value: string
      currency: string
      unit: string
      sourceAsOfDate: string
      reason: string
      evidenceRef?: string
      effectiveFrom?: string
      effectiveUntil?: string
    }

export interface EditBenchmarkInput {
  rowVersion: number
  value?: string
  effectiveFrom?: string
  effectiveUntil?: string
  sourceRateId?: string
  reason?: string
  evidenceRef?: string
}

const ADMIN = '/admin/pricing'

export const listRateSources = (signal?: AbortSignal) => apiClient.get<RateSource[]>(`${ADMIN}/sources`, { signal })

export const listSourceRates = (
  query: { seriesId?: string; batchId?: string; resolutionStatus?: string; sector?: string; eligible?: boolean; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
) => apiClient.get<SourceRate[]>(`${ADMIN}/source-rates`, { query, signal })

export const listRateSeries = (signal?: AbortSignal) => apiClient.get<RateSeries[]>(`${ADMIN}/series`, { signal })

export const getSeriesTimeline = (seriesId: string, signal?: AbortSignal) =>
  apiClient.get<SeriesTimeline>(`${ADMIN}/series/${seriesId}/timeline`, { signal })

export const listAdminBenchmarks = (query: { status?: BenchmarkStatus; seriesId?: string; limit?: number } = {}, signal?: AbortSignal) =>
  apiClient.get<BenchmarkAdmin[]>(`${ADMIN}/benchmarks`, { query, signal })

export const getAdminBenchmark = (id: string, signal?: AbortSignal) => apiClient.get<BenchmarkAdmin>(`${ADMIN}/benchmarks/${id}`, { signal })

export const listAuditEvents = (query: { entityType?: string; entityId?: string; limit?: number } = {}, signal?: AbortSignal) =>
  apiClient.get<AuditEvent[]>(`${ADMIN}/audit`, { query, signal })

export const createBenchmark = (input: CreateBenchmarkInput) => apiClient.post<BenchmarkAdmin>(`${ADMIN}/benchmarks`, input)

export const editBenchmark = (id: string, input: EditBenchmarkInput) => apiClient.patch<BenchmarkAdmin>(`${ADMIN}/benchmarks/${id}`, input)

export const submitBenchmark = (id: string) => apiClient.post<BenchmarkAdmin>(`${ADMIN}/benchmarks/${id}/submit`)

export const publishBenchmark = (id: string) => apiClient.post<BenchmarkAdmin>(`${ADMIN}/benchmarks/${id}/publish`)

export const rejectBenchmark = (id: string, reason: string) => apiClient.post<BenchmarkAdmin>(`${ADMIN}/benchmarks/${id}/reject`, { reason })

export const withdrawBenchmark = (id: string, reason: string) => apiClient.post<BenchmarkAdmin>(`${ADMIN}/benchmarks/${id}/withdraw`, { reason })
