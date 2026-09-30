export const paths = {
  marketplace: '/',
  catalogue: '/catalogue',
  productDetail: (sku: string) => `/catalogue/${encodeURIComponent(sku)}`,
  liveRates: '/live-rates',
  freightCalculator: '/freight-calculator',
  purchaseRequests: '/purchase-requests',
  negotiations: '/negotiations',
  orders: '/orders',
  orderTracking: '/order-tracking',
  reorder: '/reorder',
  dashboard: '/dashboard',
  supplierHome: '/supplier',
  listings: '/listings',
  itemMaster: '/admin/item-master',
  rateManagement: '/admin/rate-management',
  freightManagement: '/admin/freight',
  users: '/admin/users',
  approvals: '/approvals',
  company: '/company',
  supplier: (organisationId: string) => `/suppliers/${encodeURIComponent(organisationId)}`,
} as const

export interface RouteHandle {
  title: string
}
