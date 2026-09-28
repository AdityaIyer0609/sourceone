import {
  Activity,
  Boxes,
  CircleDollarSign,
  Gauge,
  Home,
  MessageSquareText,
  PackageCheck,
  RefreshCw,
  ShoppingBag,
  Store,
  Truck,
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
  { label: 'Negotiations', to: paths.negotiations, icon: MessageSquareText, badge: 3 },
  { label: 'Orders', to: paths.orders, icon: ShoppingBag },
  { label: 'Order Tracking', to: paths.orderTracking, icon: PackageCheck },
  { label: 'Reorder', to: paths.reorder, icon: RefreshCw },
]

export const controlCentreNav: NavItem[] = [
  { label: 'Dashboard', to: paths.dashboard, icon: Gauge },
  { label: 'Item Master', to: paths.itemMaster, icon: Boxes },
  { label: 'Rate Management', to: paths.rateManagement, icon: CircleDollarSign },
]
