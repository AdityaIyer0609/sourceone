import type { BenchmarkSummary, HistoryPoint, Money } from './api/pricing'

// Display-only helpers. Every number shown comes from the backend; nothing here derives prices.

const SYMBOLS: Record<string, string> = { INR: '₹', USD: '$' }
const BUSINESS_TIME_ZONE = 'Asia/Kolkata'

export function currencySymbol(currency: string) {
  return SYMBOLS[currency] ?? `${currency} `
}

function numberText(amount: string, currency: string, maxDigits?: number) {
  return Number(amount).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: maxDigits ?? (currency === 'INR' ? 2 : 4),
  })
}

export function formatMoney(money: Money, maxDigits?: number) {
  return `${currencySymbol(money.currency)}${numberText(money.amount, money.currency, maxDigits)}`
}

export function formatSignedMoney(money: Money) {
  const negative = money.amount.trim().startsWith('-')
  const magnitude = negative ? money.amount.trim().slice(1) : money.amount
  return `${negative ? '−' : '+'}${formatMoney({ ...money, amount: magnitude })}`
}

export function formatPercent(percent: string) {
  const value = Number(percent)
  return `${value < 0 ? '−' : '+'}${Math.abs(value).toFixed(2)}%`
}

/** "2026-09-25" → "25 Sep 2026" without shifting the calendar day. */
export function formatDate(isoDate: string) {
  const [year, month, day] = isoDate.slice(0, 10).split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' })
}

export function formatDateTime(isoDateTime: string) {
  return new Date(isoDateTime).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: BUSINESS_TIME_ZONE })
}

export function formatShortDay(date: Date, withTime = false) {
  return date.toLocaleString('en-IN', withTime ? { hour: '2-digit', minute: '2-digit', timeZone: BUSINESS_TIME_ZONE } : { day: '2-digit', month: 'short', timeZone: BUSINESS_TIME_ZONE })
}

export function formatClock(date: Date) {
  return date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', timeZone: BUSINESS_TIME_ZONE })
}

export function titleCase(value: string) {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function toScaled(value: string) {
  const [whole, fraction = ''] = value.trim().split('.')
  return { digits: BigInt(`${whole}${fraction}` || '0'), scale: fraction.length }
}

/**
 * Exact quantity × unit price rounded half-up to 2 decimals, matching the backend's order total.
 * Used only to preview the total in the order confirmation; the placed order's total comes from the API.
 */
export function previewOrderTotal(quantity: string, unitPrice: Money): Money {
  const a = toScaled(quantity)
  const b = toScaled(unitPrice.amount)
  const product = a.digits * b.digits
  const scale = a.scale + b.scale
  let cents: bigint
  if (scale <= 2) {
    cents = product * 10n ** BigInt(2 - scale)
  } else {
    const divisor = 10n ** BigInt(scale - 2)
    cents = product / divisor
    if ((product % divisor) * 2n >= divisor) cents += 1n
  }
  return { amount: `${cents / 100n}.${(cents % 100n).toString().padStart(2, '0')}`, currency: unitPrice.currency }
}

/** Catalogue glyph for benchmark series; all current SourceOne series are polymers. */
export const BENCHMARK_GLYPH = 'RESIN'

export function movementDirection(benchmark: BenchmarkSummary): 'up' | 'down' | null {
  const { movement } = benchmark
  if (movement.state !== 'ok' || movement.percent === null) return null
  return Number(movement.percent) < 0 ? 'down' : 'up'
}

export function sparklineValues(points: HistoryPoint[]) {
  return points.map((point) => Number(point.value))
}

/** Scales values into an SVG box; returns an empty path when fewer than two points exist. */
export function linePath(values: number[], width: number, height: number, pad = 2) {
  if (values.length < 2) return ''
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const step = (width - pad * 2) / (values.length - 1)
  return values
    .map((value, index) => {
      const x = pad + index * step
      const y = max === min ? height / 2 : pad + (1 - (value - min) / span) * (height - pad * 2)
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(' ')
}
