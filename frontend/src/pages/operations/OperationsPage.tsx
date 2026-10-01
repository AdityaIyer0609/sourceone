import { Navigate } from "react-router-dom";
import { canAccess } from "../../app/navigation";
import { paths } from "../../app/paths";
import { Heading } from "../../components/ui";
import { readSession } from "../../lib/api/auth";
import { DashboardWorkspace } from "./DashboardWorkspace";
import { FreightManagement } from "./FreightManagement";
import { ItemMasterWorkspace } from "./ItemMasterWorkspace";
import { FreightWorkbench } from "./FreightWorkbench";
import { operationsConfigs, type OperationsScreen } from "./operationsConfig";
import { OrdersWorkspace } from "./OrdersWorkspace";
import { PurchaseRequestsWorkspace } from "./PurchaseRequestsWorkspace";
import { ReorderWorkspace } from "./ReorderWorkspace";
import { RateManagementWorkspace } from "./RateManagementWorkspace";
import { TrackingView } from "./TrackingView";
import { UsersWorkspace } from "./UsersWorkspace";
import { ApprovalsWorkspace } from "./ApprovalsWorkspace";
import { CompanyWorkspace } from "./CompanyWorkspace";
import { ListingsWorkspace } from "./ListingsWorkspace";
import { SupplierFreightWorkspace } from "./SupplierFreightWorkspace";
import { SupplierHome } from "./SupplierHome";

const screenRoles: Record<OperationsScreen, readonly string[]> = {
  "Freight Calculator": ["platform_admin", "pricing_admin", "buyer", "supplier"],
  "Purchase Requests": ["buyer", "supplier"],
  Orders: ["buyer", "supplier"],
  "Order Tracking": ["buyer", "supplier"],
  Reorder: ["buyer"],
  Dashboard: ["buyer"],
  "Supplier Home": ["supplier"],
  Listings: ["supplier"],
  "Your freight": ["supplier"],
  "Item Master": ["platform_admin", "pricing_admin"],
  "Rate Management": ["platform_admin", "pricing_admin"],
  "Freight Management": ["platform_admin", "pricing_admin"],
  "User Management": ["platform_admin"],
  Approvals: ["approver"],
  Company: ["approver"],
};

export function OperationsPage({ screen }: { screen: OperationsScreen }) {
  const roles = readSession()?.user.roles ?? [];
  if (!canAccess(roles, screenRoles[screen])) return <Navigate to={paths.marketplace} replace />;
  const config = operationsConfigs[screen];
  const freight = screen === "Freight Calculator";
  const freightAdmin = screen === "Freight Management";
  const tracking = screen === "Order Tracking";
  const rates = screen === "Rate Management";
  const orders = screen === "Orders";
  const reorder = screen === "Reorder";
  const dashboard = screen === "Dashboard";
  const supplierHome = screen === "Supplier Home";
  const listings = screen === "Listings";
  const ownFreight = screen === "Your freight";
  const items = screen === "Item Master";
  const requests = screen === "Purchase Requests";
  const users = screen === "User Management";
  const approvals = screen === "Approvals";
  const company = screen === "Company";
  return (
    <div className="page">
      <div className="page-heading"><div><small>{config.kicker}</small><Heading level={1}>{config.title}</Heading><p>{config.description}</p></div></div>
      {freight ? <FreightWorkbench /> : freightAdmin ? <FreightManagement /> : tracking ? <TrackingView /> : rates ? <RateManagementWorkspace /> : orders ? <OrdersWorkspace /> : reorder ? <ReorderWorkspace /> : dashboard ? <DashboardWorkspace /> : supplierHome ? <SupplierHome /> : listings ? <ListingsWorkspace /> : ownFreight ? <SupplierFreightWorkspace /> : items ? <ItemMasterWorkspace /> : requests ? <PurchaseRequestsWorkspace /> : users ? <UsersWorkspace /> : approvals ? <ApprovalsWorkspace /> : company ? <CompanyWorkspace /> : null}
    </div>
  );
}
