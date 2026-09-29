export type OperationsScreen =
  | 'Freight Calculator'
  | 'Purchase Requests'
  | 'Orders'
  | 'Order Tracking'
  | 'Reorder'
  | 'Dashboard'
  | 'Item Master'
  | 'Rate Management'
  | 'Freight Management'
  | 'User Management'

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
  'Purchase Requests': { kicker: 'PURCHASE OPERATIONS', title: 'Purchase requests', description: 'Ask an eligible supplier for a product. Sending opens a negotiation and does not place an order.', action: 'New request', actionUnavailable: 'Use New request in the list. Choose a product, quantity, delivery PIN and an optional supplier.' },
  Orders: { kicker: 'PURCHASE OPERATIONS', title: 'Orders', description: 'A unified commercial view from approved PO to invoice.', action: 'Create order', actionUnavailable: 'Orders are created from an accepted negotiation. Open it in Negotiations and choose Create order.' },
  'Order Tracking': { kicker: 'CONTROL TOWER', title: 'Order tracking', description: 'Live dispatch, route and delivery milestones across your network.', action: 'Track shipment', actionUnavailable: 'Live GPS tracking is not available. Milestones are updated by the supplier.' },
  Reorder: { kicker: 'PURCHASE HISTORY', title: 'Reorder centre', description: "Repeat proven purchases with today's rate and terms.", action: 'Build reorder', actionUnavailable: 'Choose Reorder on a past order. It starts a new negotiation at the current asking price.' },
  Dashboard: { kicker: 'CUSTOMER INTELLIGENCE', title: 'Procurement dashboard', description: 'Spend, savings and supply performance across your organization.', action: 'Export report', actionUnavailable: 'Export is not available. Figures are your SourceOne orders and negotiations.' },
  'Item Master': { kicker: 'ADMINISTRATION', title: 'Item master', description: 'Govern normalized specifications, SKUs and procurement controls.', action: 'Add item', actionUnavailable: 'Add a SourceOne product in the form below. Products used by an order are deactivated, not deleted.' },
  'Rate Management': { kicker: 'COMMERCIAL ADMIN', title: 'Rate management', description: 'Publish benchmarks, review submissions and maintain rate integrity.', action: 'Publish rates', actionUnavailable: 'Bulk publishing is not available. Publish each benchmark from the review queue.' },
  'Freight Management': { kicker: 'COMMERCIAL ADMIN', title: 'Freight rules', description: 'SourceOne freight lanes used only to estimate landed cost.', action: 'Add rule', actionUnavailable: 'Add or edit a lane in the form below. Freight stays an estimate.' },
  'User Management': { kicker: 'ADMINISTRATION', title: 'User management', description: 'Create SourceOne accounts and assign a role. Only a platform admin can do this.', action: 'Add user', actionUnavailable: 'Add a user in the form below. A deactivated user cannot sign in.' },
}
