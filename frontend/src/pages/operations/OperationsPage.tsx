import { ArrowRight } from "lucide-react";
import { Button, Heading } from "../../components/ui";
import { DataWorkspace } from "./DataWorkspace";
import { FreightWorkbench } from "./FreightWorkbench";
import { operationsConfigs, type OperationsScreen } from "./operationsConfig";
import { TrackingView } from "./TrackingView";

export function OperationsPage({ screen }: { screen: OperationsScreen }) {
  const config = operationsConfigs[screen];
  const freight = screen === "Freight Calculator";
  const tracking = screen === "Order Tracking";
  return (
    <div className="page">
      <div className="page-heading"><div><small>{config.kicker}</small><Heading level={1}>{config.title}</Heading><p>{config.description}</p></div><Button>{config.action} <ArrowRight size={16}/></Button></div>
      {freight ? <FreightWorkbench /> : tracking ? <TrackingView /> : <DataWorkspace screen={screen} />}
    </div>
  );
}
