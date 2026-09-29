import { ArrowRight } from "lucide-react";
import { Button, Heading } from "../../components/ui";
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

export function OperationsPage({ screen }: { screen: OperationsScreen }) {
  const config = operationsConfigs[screen];
  const freight = screen === "Freight Calculator";
  const freightAdmin = screen === "Freight Management";
  const tracking = screen === "Order Tracking";
  const rates = screen === "Rate Management";
  const orders = screen === "Orders";
  const reorder = screen === "Reorder";
  const dashboard = screen === "Dashboard";
  const items = screen === "Item Master";
  const requests = screen === "Purchase Requests";
  const users = screen === "User Management";
  return (
    <div className="page">
      <div className="page-heading"><div><small>{config.kicker}</small><Heading level={1}>{config.title}</Heading><p>{config.description}</p></div><Button aria-disabled={config.actionUnavailable ? "true" : undefined} title={config.actionUnavailable}>{config.action} <ArrowRight size={16}/></Button></div>
      {freight ? <FreightWorkbench /> : freightAdmin ? <FreightManagement /> : tracking ? <TrackingView /> : rates ? <RateManagementWorkspace /> : orders ? <OrdersWorkspace /> : reorder ? <ReorderWorkspace /> : dashboard ? <DashboardWorkspace /> : items ? <ItemMasterWorkspace /> : requests ? <PurchaseRequestsWorkspace /> : users ? <UsersWorkspace /> : null}
    </div>
  );
}
