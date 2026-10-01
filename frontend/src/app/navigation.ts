import {
  Activity,
  Building2,
  Boxes,
  ClipboardCheck,
  CircleDollarSign,
  Gauge,
  Home,
  MessageSquareText,
  ReceiptText,
  PackageCheck,
  RefreshCw,
  Tags,
  ShoppingBag,
  Store,
  Truck,
  User,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { paths } from './paths'

export type AppRole = 'platform_admin' | 'pricing_admin' | 'buyer' | 'supplier' | 'approver'

const view: AppRole[] = ['platform_admin', 'pricing_admin', 'buyer', 'supplier', 'approver']
const trading: AppRole[] = ['buyer', 'supplier']
const buying: AppRole[] = ['buyer']
const supplying: AppRole[] = ['supplier']
const pricing: AppRole[] = ['platform_admin', 'pricing_admin']

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  badge?: number
  /** Roles that can open this screen. Others do not see it. */
  roles: AppRole[]
}

export const commerceNav: NavItem[] = [
  { label: 'Marketplace', to: paths.marketplace, icon: Home, roles: view },
  { label: 'Catalogue', to: paths.catalogue, icon: Store, roles: view },
  { label: 'Live Rates', to: paths.liveRates, icon: Activity, roles: view },
  { label: 'Freight Calculator', to: paths.freightCalculator, icon: Truck, roles: view },
  { label: 'Purchase Requests', to: paths.purchaseRequests, icon: ReceiptText, roles: trading },
  { label: 'Negotiations', to: paths.negotiations, icon: MessageSquareText, roles: trading },
  { label: 'Orders', to: paths.orders, icon: ShoppingBag, roles: trading },
  { label: 'Order Tracking', to: paths.orderTracking, icon: PackageCheck, roles: trading },
  { label: 'Reorder', to: paths.reorder, icon: RefreshCw, roles: buying },
  { label: 'Listings', to: paths.listings, icon: Tags, roles: supplying },
  { label: 'Your freight', to: paths.supplierFreight, icon: Truck, roles: supplying },
  { label: 'Approvals', to: paths.approvals, icon: ClipboardCheck, roles: ['approver'] },
]

export const controlCentreNav: NavItem[] = [
  { label: 'Dashboard', to: paths.dashboard, icon: Gauge, roles: buying },
  { label: 'Dashboard', to: paths.supplierHome, icon: Gauge, roles: supplying },
  { label: 'Item Master', to: paths.itemMaster, icon: Boxes, roles: pricing },
  { label: 'Rate Management', to: paths.rateManagement, icon: CircleDollarSign, roles: pricing },
  { label: 'Freight', to: paths.freightManagement, icon: Truck, roles: pricing },
  { label: 'User Management', to: paths.users, icon: Users, roles: ['platform_admin'] },
  { label: 'Company', to: paths.company, icon: Building2, roles: ['approver'] },
]

export const accountNav: NavItem[] = [
  { label: 'Profile', to: paths.profile, icon: User, roles: view },
]

export function canAccess(roles: readonly string[], allowed: readonly string[]) {
  return roles.some((role) => allowed.includes(role))
}

export function visibleNav(items: NavItem[], roles: readonly string[]) {
  return items.filter((item) => canAccess(roles, item.roles))
}
