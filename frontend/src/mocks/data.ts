// Temporary mock data carried over from the Figma Make prototype.
// Replace with API calls as each backend feature lands.

export interface Product {
  id: string
  name: string
  category: string
  price: number
  uom: string
  change: number
  stock: string
  city: string
  glyph: string
}

export type RateRow = [material: string, sku: string, rate: string, change: string, changePct: string, market: string, updated: string]

export interface NegotiationOffer {
  v: number
  price: string
  freight: string
  credit: string
  note: string
  time: string
}

export const heroImage =
  'https://images.unsplash.com/photo-1697698532634-ea59b636ccea?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=86&w=1600'

export const products: Product[] = [
  { id: 'CR-304', name: 'SS 304 Cold Rolled Coil', category: 'Stainless Steel', price: 214.8, uom: 'kg', change: 1.24, stock: 'Ready stock', city: 'Ahmedabad', glyph: 'COIL' },
  { id: 'HR-2062', name: 'HR Sheet IS 2062 E250', category: 'Carbon Steel', price: 58.45, uom: 'kg', change: -0.62, stock: '2–3 days', city: 'Mumbai', glyph: 'SHEET' },
  { id: 'AL-6061', name: 'Aluminium 6061 Plate', category: 'Non-ferrous', price: 284.2, uom: 'kg', change: 2.18, stock: 'Ready stock', city: 'Pune', glyph: 'PLATE' },
  { id: 'PP-T30', name: 'PP Granules T30S', category: 'Polymers', price: 94.75, uom: 'kg', change: 0.38, stock: 'Ready stock', city: 'Dahej', glyph: 'RESIN' },
  { id: 'CU-C110', name: 'Copper Sheet C11000', category: 'Non-ferrous', price: 824.6, uom: 'kg', change: -1.12, stock: 'On request', city: 'Delhi NCR', glyph: 'SHEET' },
  { id: 'MS-PIPE', name: 'MS ERW Pipe — Medium', category: 'Pipes & Tubes', price: 71.25, uom: 'kg', change: 0.84, stock: 'Ready stock', city: 'Raipur', glyph: 'PIPE' },
]

export const rateRows: RateRow[] = [
  ['SS 304 CR Coil', 'CR-304', '₹214.80', '+₹2.63', '+1.24%', 'Mumbai', '09:42'],
  ['HR Sheet E250', 'HR-2062', '₹58.45', '−₹0.36', '−0.62%', 'Mumbai', '09:38'],
  ['Aluminium 6061', 'AL-6061', '₹284.20', '+₹6.08', '+2.18%', 'Pune', '09:35'],
  ['PP Granules T30S', 'PP-T30', '₹94.75', '+₹0.36', '+0.38%', 'Dahej', '09:31'],
  ['Copper Sheet C110', 'CU-C110', '₹824.60', '−₹9.33', '−1.12%', 'Delhi', '09:28'],
]

export const marketplaceCategories: [glyph: string, name: string, count: string][] = [
  ['COIL', 'Stainless steel', '1,284 SKUs'],
  ['SHEET', 'Sheets & plates', '946 SKUs'],
  ['PIPE', 'Pipes & tubes', '713 SKUs'],
  ['RESIN', 'Polymers', '534 SKUs'],
  ['PLATE', 'Non-ferrous', '468 SKUs'],
]

export const negotiationOffers: NegotiationOffer[] = [
  { v: 3, price: '₹208.40/kg', freight: 'Included', credit: '30 days', note: 'Current supplier offer', time: 'Today, 10:42' },
  { v: 2, price: '₹211.00/kg', freight: '₹1.90/kg', credit: '15 days', note: 'Your counter offer', time: 'Yesterday, 16:18' },
  { v: 1, price: '₹216.25/kg', freight: '₹2.10/kg', credit: 'Advance', note: 'Initial supplier offer', time: '12 May, 11:05' },
]

export const workspaceRows: [reference: string, material: string, quantity: string, value: string, status: string, updated: string][] = [
  ['SO-4857', 'SS 304 Cold Rolled Coil', '12,000 kg', '₹25,00,800', 'In transit', '10 min ago'],
  ['PO-4563', 'PP Granules T30S', '8,000 kg', '₹7,58,000', 'Processing', '42 min ago'],
  ['RFQ-9281', 'Aluminium 6061 Plate', '2,500 kg', '₹7,10,500', 'Action needed', '2 hrs ago'],
  ['SO-4521', 'MS ERW Pipe — Medium', '6,400 kg', '₹4,56,000', 'Confirmed', 'Yesterday'],
  ['PO-4498', 'HR Sheet IS 2062 E250', '18,000 kg', '₹10,52,100', 'Delivered', '08 May'],
]

export const shipmentTimeline: [milestone: string, time: string][] = [
  ['Order confirmed', '12 May · 10:42'],
  ['Material inspected', '13 May · 14:20'],
  ['Dispatched', 'Today · 08:10'],
  ['In transit', 'Current milestone'],
  ['Delivered', 'Expected · 17:30'],
]
