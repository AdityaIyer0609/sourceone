export type OperationsScreen =
  | 'Freight Calculator'
  | 'Orders'
  | 'Order Tracking'
  | 'Reorder'
  | 'Dashboard'
  | 'Item Master'
  | 'Rate Management'

export interface OperationsConfig {
  kicker: string
  title: string
  description: string
  action: string
  /** Set when the header action has no backend equivalent yet; the button keeps its look but does nothing. */
  actionUnavailable?: string
}

export const operationsConfigs: Record<OperationsScreen, OperationsConfig> = {
  'Freight Calculator': { kicker: 'LANDED COST WORKBENCH', title: 'Purchase & freight calculator', description: 'Compare supply points and know the landed cost before raising a request.', action: 'Calculate route' },
  Orders: { kicker: 'PURCHASE OPERATIONS', title: 'Orders', description: 'A unified commercial view from approved PO to invoice.', action: 'Create order', actionUnavailable: 'Orders are created from an accepted negotiation. Open it in Negotiations and choose Create order.' },
  'Order Tracking': { kicker: 'CONTROL TOWER', title: 'Order tracking', description: 'Live dispatch, route and delivery milestones across your network.', action: 'Track shipment', actionUnavailable: 'Live GPS tracking is not available. Milestones are updated by the supplier.' },
  Reorder: { kicker: 'PURCHASE HISTORY', title: 'Reorder centre', description: "Repeat proven purchases with today's rate and terms.", action: 'Build reorder' },
  Dashboard: { kicker: 'CUSTOMER INTELLIGENCE', title: 'Procurement dashboard', description: 'Spend, savings and supply performance across your organization.', action: 'Export report' },
  'Item Master': { kicker: 'ADMINISTRATION', title: 'Item master', description: 'Govern normalized specifications, SKUs and procurement controls.', action: 'Add item' },
  'Rate Management': { kicker: 'COMMERCIAL ADMIN', title: 'Rate management', description: 'Publish benchmarks, review submissions and maintain rate integrity.', action: 'Publish rates', actionUnavailable: 'Bulk publishing is not available. Publish each benchmark from the review queue.' },
}
