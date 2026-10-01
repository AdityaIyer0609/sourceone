export type OperationsScreen =
  | 'Freight Calculator'
  | 'Purchase Requests'
  | 'Orders'
  | 'Order Tracking'
  | 'Reorder'
  | 'Dashboard'
  | 'Supplier Home'
  | 'Listings'
  | 'Your freight'
  | 'Item Master'
  | 'Rate Management'
  | 'Freight Management'
  | 'User Management'
  | 'Approvals'
  | 'Company'

export interface OperationsConfig {
  kicker: string
  title: string
  description: string
}

export const operationsConfigs: Record<OperationsScreen, OperationsConfig> = {
  'Freight Calculator': { kicker: 'LANDED COST WORKBENCH', title: 'Purchase & freight calculator', description: 'Compare supply points and know the landed cost before raising a request.' },
  'Purchase Requests': { kicker: 'PURCHASE OPERATIONS', title: 'Purchase requests', description: 'Ask an eligible supplier for a product. Sending opens a negotiation and does not place an order.' },
  Orders: { kicker: 'PURCHASE OPERATIONS', title: 'Orders', description: 'A unified commercial view from approved PO to invoice.' },
  'Order Tracking': { kicker: 'CONTROL TOWER', title: 'Order tracking', description: 'Live dispatch, route and delivery milestones across your network.' },
  Reorder: { kicker: 'PURCHASE HISTORY', title: 'Reorder centre', description: "Repeat proven purchases with today's rate and terms." },
  Dashboard: { kicker: 'CUSTOMER INTELLIGENCE', title: 'Procurement dashboard', description: 'Spend, savings and supply performance across your organization.' },
  'Supplier Home': { kicker: 'SUPPLIER', title: 'Your work', description: 'Requests, negotiations, and orders that are waiting on you, plus your own listings and performance.' },
  Listings: { kicker: 'SUPPLIER', title: 'Listings', description: 'Your asking prices, catalogue products you can list at your own price, and new products submitted for a pricing admin to accept. Saving a price updates a listing. It does not publish a benchmark.' },
  'Your freight': { kicker: 'SUPPLIER', title: 'Your freight', description: 'Saved lanes are used when a buyer’s PIN matches. A rate per km is used only when it does not. Neither one changes your asking price or an order total.' },
  'Item Master': { kicker: 'ADMINISTRATION', title: 'Item master', description: 'Govern normalized specifications, SKUs and procurement controls.' },
  'Rate Management': { kicker: 'COMMERCIAL ADMIN', title: 'Rate management', description: 'Publish benchmarks, review submissions and maintain rate integrity.' },
  'Freight Management': { kicker: 'COMMERCIAL ADMIN', title: 'Freight rules', description: 'Plenza freight lanes used only to estimate landed cost.' },
  'User Management': { kicker: 'ADMINISTRATION', title: 'User management', description: 'Create Plenza accounts and assign a role. Only a platform admin can do this.' },
  Approvals: { kicker: 'COMPANY', title: 'Approvals', description: 'Orders above the company material threshold wait here. Approving places the order. Declining leaves the negotiation accepted.' },
  Company: { kicker: 'COMPANY', title: 'Company', description: 'People in this company, and the material total that needs a second person before an order is placed.' },
}
