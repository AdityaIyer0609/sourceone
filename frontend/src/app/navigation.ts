import {
  Activity,
  Boxes,
  CircleDollarSign,
  Gauge,
  Home,
  MessageSquareText,
  ReceiptText,
  PackageCheck,
  RefreshCw,
  ShoppingBag,
  Store,
  Truck,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { paths } from './paths'

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  badge?: number
}

export const commerceNav: NavItem[] = [
  { label: 'Marketplace', to: paths.marketplace, icon: Home },
  { label: 'Catalogue', to: paths.catalogue, icon: Store },
  { label: 'Live Rates', to: paths.liveRates, icon: Activity },
  { label: 'Freight Calculator', to: paths.freightCalculator, icon: Truck },
  { label: 'Purchase Requests', to: paths.purchaseRequests, icon: ReceiptText },
  { label: 'Negotiations', to: paths.negotiations, icon: MessageSquareText },
  { label: 'Orders', to: paths.orders, icon: ShoppingBag },
  { label: 'Order Tracking', to: paths.orderTracking, icon: PackageCheck },
  { label: 'Reorder', to: paths.reorder, icon: RefreshCw },
]

export const controlCentreNav: NavItem[] = [
  { label: 'Dashboard', to: paths.dashboard, icon: Gauge },
  { label: 'Item Master', to: paths.itemMaster, icon: Boxes },
  { label: 'Rate Management', to: paths.rateManagement, icon: CircleDollarSign },
  { label: 'Freight', to: paths.freightManagement, icon: Truck },
  { label: 'User Management', to: paths.users, icon: Users },
]
