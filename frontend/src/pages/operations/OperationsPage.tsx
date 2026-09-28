import { ArrowRight } from "lucide-react";
import { Button, Heading } from "../../components/ui";
import { DataWorkspace } from "./DataWorkspace";
import { FreightWorkbench } from "./FreightWorkbench";
import { operationsConfigs, type OperationsScreen } from "./operationsConfig";
import { OrdersWorkspace } from "./OrdersWorkspace";
import { RateManagementWorkspace } from "./RateManagementWorkspace";
import { TrackingView } from "./TrackingView";

export function OperationsPage({ screen }: { screen: OperationsScreen }) {
  const config = operationsConfigs[screen];
  const freight = screen === "Freight Calculator";
  const tracking = screen === "Order Tracking";
  const rates = screen === "Rate Management";
  const orders = screen === "Orders";
  return (
    <div className="page">
      <div className="page-heading"><div><small>{config.kicker}</small><Heading level={1}>{config.title}</Heading><p>{config.description}</p></div><Button aria-disabled={config.actionUnavailable ? "true" : undefined} title={config.actionUnavailable}>{config.action} <ArrowRight size={16}/></Button></div>
      {freight ? <FreightWorkbench /> : tracking ? <TrackingView /> : rates ? <RateManagementWorkspace /> : orders ? <OrdersWorkspace /> : <DataWorkspace screen={screen} />}
    </div>
  );
}
