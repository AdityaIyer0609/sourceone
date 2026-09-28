// Temporary mock data carried over from the Figma Make prototype.
// Replace with API calls as each backend feature lands. Pricing now comes from the
// SourceOne benchmark API (src/lib/api/pricing.ts); negotiations from src/lib/api/negotiations.ts.

export const heroImage =
  'https://images.unsplash.com/photo-1697698532634-ea59b636ccea?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=86&w=1600'

export const marketplaceCategories: [glyph: string, name: string, count: string][] = [
  ['COIL', 'Stainless steel', '1,284 SKUs'],
  ['SHEET', 'Sheets & plates', '946 SKUs'],
  ['PIPE', 'Pipes & tubes', '713 SKUs'],
  ['RESIN', 'Polymers', '534 SKUs'],
  ['PLATE', 'Non-ferrous', '468 SKUs'],
]

export const workspaceRows: [reference: string, material: string, quantity: string, value: string, status: string, updated: string][] = [
  ['SO-4857', 'SS 304 Cold Rolled Coil', '12,000 kg', '₹25,00,800', 'In transit', '10 min ago'],
  ['PO-4563', 'PP Granules T30S', '8,000 kg', '₹7,58,000', 'Processing', '42 min ago'],
  ['RFQ-9281', 'Aluminium 6061 Plate', '2,500 kg', '₹7,10,500', 'Action needed', '2 hrs ago'],
  ['SO-4521', 'MS ERW Pipe — Medium', '6,400 kg', '₹4,56,000', 'Confirmed', 'Yesterday'],
  ['PO-4498', 'HR Sheet IS 2062 E250', '18,000 kg', '₹10,52,100', 'Delivered', '08 May'],
]
