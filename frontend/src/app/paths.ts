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
  itemMaster: '/admin/item-master',
  rateManagement: '/admin/rate-management',
  freightManagement: '/admin/freight',
  users: '/admin/users',
} as const

export interface RouteHandle {
  title: string
}
