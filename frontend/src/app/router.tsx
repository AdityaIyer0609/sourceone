import { createBrowserRouter } from 'react-router-dom'
import { RouteErrorBoundary } from '../components/feedback/RouteErrorBoundary'
import { AppShell } from '../components/layout/AppShell'
import { CataloguePage } from '../pages/CataloguePage'
import { LiveRatesPage } from '../pages/LiveRatesPage'
import { MarketplacePage } from '../pages/MarketplacePage'
import { NegotiationsPage } from '../pages/NegotiationsPage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { OperationsPage } from '../pages/operations/OperationsPage'
import { ProductDetailPage } from '../pages/ProductDetailPage'
import { ProfilePage } from '../pages/ProfilePage'
import { SupplierProfilePage } from '../pages/SupplierProfilePage'
import type { RouteHandle } from './paths'

const title = (value: string): RouteHandle => ({ title: value })

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    errorElement: <RouteErrorBoundary />,
    children: [
      {
        // Pathless layout route so page errors render inside the app shell.
        errorElement: <RouteErrorBoundary />,
        children: [
          { index: true, element: <MarketplacePage />, handle: title('Marketplace') },
          { path: 'catalogue', element: <CataloguePage />, handle: title('Catalogue') },
          { path: 'catalogue/:sku', element: <ProductDetailPage />, handle: title('Product Detail') },
          { path: 'suppliers/:organisationId', element: <SupplierProfilePage />, handle: title('Supplier') },
          { path: 'live-rates', element: <LiveRatesPage />, handle: title('Live Rates') },
          { path: 'freight-calculator', element: <OperationsPage screen="Freight Calculator" />, handle: title('Freight Calculator') },
          { path: 'purchase-requests', element: <OperationsPage screen="Purchase Requests" />, handle: title('Purchase Requests') },
          { path: 'negotiations', element: <NegotiationsPage />, handle: title('Negotiations') },
          { path: 'orders', element: <OperationsPage screen="Orders" />, handle: title('Orders') },
          { path: 'order-tracking', element: <OperationsPage screen="Order Tracking" />, handle: title('Order Tracking') },
          { path: 'reorder', element: <OperationsPage screen="Reorder" />, handle: title('Reorder') },
          { path: 'dashboard', element: <OperationsPage screen="Dashboard" />, handle: title('Dashboard') },
          { path: 'supplier', element: <OperationsPage screen="Supplier Home" />, handle: title('Supplier') },
          { path: 'listings', element: <OperationsPage screen="Listings" />, handle: title('Listings') },
          { path: 'freight', element: <OperationsPage screen="Your freight" />, handle: title('Your freight') },
          { path: 'admin/item-master', element: <OperationsPage screen="Item Master" />, handle: title('Item Master') },
          { path: 'admin/rate-management', element: <OperationsPage screen="Rate Management" />, handle: title('Rate Management') },
          { path: 'admin/freight', element: <OperationsPage screen="Freight Management" />, handle: title('Freight') },
          { path: 'admin/users', element: <OperationsPage screen="User Management" />, handle: title('User Management') },
          { path: 'approvals', element: <OperationsPage screen="Approvals" />, handle: title('Approvals') },
          { path: 'assign-orders', element: <OperationsPage screen="Assign orders" />, handle: title('Assign orders') },
          { path: 'company', element: <OperationsPage screen="Company" />, handle: title('Company') },
          { path: 'profile', element: <ProfilePage />, handle: title('Profile') },
          { path: '*', element: <NotFoundPage />, handle: title('Not Found') },
        ],
      },
    ],
  },
])
