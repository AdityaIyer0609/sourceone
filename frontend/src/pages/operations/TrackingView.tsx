import { Truck } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { OrderTimeline } from "../../components/order/OrderTimeline";
import { OrgLink } from "../../components/supplier/OrgLink";
import { Button, Heading, Input } from "../../components/ui";
import { ApiError, getErrorMessage } from "../../lib/api/client";
import { changeOrderStatus, downloadOrderDocument, getOrderTracking, listOrders, saveShipment, type OrderTracking, type ShipmentDetails } from "../../lib/api/orders";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatDate, formatDateTime, formatMoney, titleCase } from "../../lib/pricingFormat";
import { OrderStatusBadge } from "./OrdersWorkspace";

function milestone(tracking: OrderTracking, status: "dispatched" | "delivered", pending: string) {
  const at = tracking.steps.find((step) => step.status === status)?.at;
  return at ? `${titleCase(status)} · ${formatDateTime(at)}` : pending;
}

function delayText(tracking: OrderTracking) {
  if (!tracking.requiredBy) return "No required date is stored, so a delay is not shown.";
  if (tracking.delayed) return `Past the required date of ${formatDate(tracking.requiredBy)}.`;
  return `Required by ${formatDate(tracking.requiredBy)}.`;
}

function blankShipment(shipment: ShipmentDetails): ShipmentDetails {
  return {
    lrNumber: shipment.lrNumber ?? "",
    transporter: shipment.transporter ?? "",
    vehicle: shipment.vehicle ?? "",
    eta: shipment.eta ?? "",
  };
}

function StatusAction({ tracking, onChanged }: { tracking: OrderTracking; onChanged: () => void }) {
  const [note, setNote] = useState("");
  const [shipment, setShipment] = useState<ShipmentDetails>(() => blankShipment(tracking.shipment));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const next = tracking.nextStatus;
  if (!tracking.canProgress || !next) return null;
  const dispatching = next === "dispatched";
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const saved = dispatching ? {
        lrNumber: shipment.lrNumber?.trim() || null,
        transporter: shipment.transporter?.trim() || null,
        vehicle: shipment.vehicle?.trim() || null,
        eta: shipment.eta || null,
      } : undefined;
      await changeOrderStatus(tracking.orderId, next, note.trim(), saved);
      setNote("");
      onChanged();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="eta-block">
      <small>NEXT STEP</small>
      {dispatching && (
        <>
          <Input placeholder="LR number (optional)" value={shipment.lrNumber ?? ""} maxLength={40} onChange={(event) => setShipment({ ...shipment, lrNumber: event.target.value })} />
          <Input placeholder="Transporter (optional)" value={shipment.transporter ?? ""} maxLength={80} onChange={(event) => setShipment({ ...shipment, transporter: event.target.value })} />
          <Input placeholder="Vehicle (optional)" value={shipment.vehicle ?? ""} maxLength={40} onChange={(event) => setShipment({ ...shipment, vehicle: event.target.value })} />
          <Input aria-label="ETA" type="date" value={shipment.eta ?? ""} onChange={(event) => setShipment({ ...shipment, eta: event.target.value })} />
        </>
      )}
      <Input placeholder="Note for the buyer (optional)" value={note} maxLength={2000} onChange={(event) => setNote(event.target.value)} />
      {error ? <p className="negative" role="alert">{getErrorMessage(error)}{error instanceof ApiError && error.code ? ` (${error.code})` : ""}</p> : null}
      <Button disabled={busy} onClick={submit}>Mark as {titleCase(next)}</Button>
    </div>
  );
}

function ShipmentFacts({ tracking, onChanged }: { tracking: OrderTracking; onChanged: () => void }) {
  const [shipment, setShipment] = useState<ShipmentDetails>(() => blankShipment(tracking.shipment));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const editable = tracking.viewerRole === "supplier" && (tracking.status === "dispatched" || tracking.status === "in_transit");
  const saved = tracking.shipment;
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await saveShipment(tracking.orderId, {
        lrNumber: shipment.lrNumber?.trim() || null,
        transporter: shipment.transporter?.trim() || null,
        vehicle: shipment.vehicle?.trim() || null,
        eta: shipment.eta || null,
      });
      onChanged();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="eta-block">
      <small>SHIPMENT</small>
      <span>No live location is stored for this order.</span>
      <strong>{saved.lrNumber ? `LR ${saved.lrNumber}` : "No LR saved."}</strong>
      <span>{saved.transporter || "No transporter saved."}{saved.vehicle ? ` · ${saved.vehicle}` : ""}</span>
      <span>{saved.eta ? `ETA ${formatDate(saved.eta)}` : "No ETA saved."}</span>
      <span>{delayText(tracking)}</span>
      {tracking.pod ? <Button variant="ghost" onClick={() => void downloadOrderDocument(tracking.orderId, tracking.pod!.id, tracking.pod!.filename)}>{`POD · ${tracking.pod.filename}`}</Button> : <span>No POD file stored.</span>}
      {editable && (
        <>
          <Input placeholder="LR number" value={shipment.lrNumber ?? ""} maxLength={40} onChange={(event) => setShipment({ ...shipment, lrNumber: event.target.value })} />
          <Input placeholder="Transporter" value={shipment.transporter ?? ""} maxLength={80} onChange={(event) => setShipment({ ...shipment, transporter: event.target.value })} />
          <Input placeholder="Vehicle" value={shipment.vehicle ?? ""} maxLength={40} onChange={(event) => setShipment({ ...shipment, vehicle: event.target.value })} />
          <Input aria-label="Update ETA" type="date" value={shipment.eta ?? ""} onChange={(event) => setShipment({ ...shipment, eta: event.target.value })} />
          {error ? <p className="negative" role="alert">{getErrorMessage(error)}{error instanceof ApiError && error.code ? ` (${error.code})` : ""}</p> : null}
          <Button variant="secondary" disabled={busy} onClick={save}>Save shipment</Button>
        </>
      )}
    </div>
  );
}

export function TrackingView() {
  const [searchParams, setSearchParams] = useSearchParams();
  const orders = useApiQuery("orders", (signal) => listOrders(signal));
  const list = orders.data ?? [];
  const selected = list.find((order) => order.id === searchParams.get("id")) ?? list[0] ?? null;
  const tracking = useApiQuery(selected ? `tracking:${selected.id}` : null, (signal) => getOrderTracking(selected!.id, signal));
  const data = tracking.data;
  const refresh = () => {
    tracking.reload();
    orders.reload();
  };

  return (
    <AsyncContent isLoading={(orders.isLoading && !list.length) || (tracking.isLoading && !data)} error={orders.error ?? tracking.error} onRetry={refresh} isEmpty={!orders.isLoading && !list.length} emptyTitle="No orders to track" emptyMessage="Orders appear here once they are placed from an accepted negotiation." loadingLabel="Loading tracking…">
      <section className="section-block data-section">
        <div className="market-table-wrap">
          <table className="market-table tracking-orders">
            <thead>
              <tr>
                <th>Order</th>
                <th>Product</th>
                <th>Quantity</th>
                <th>Counterparty</th>
                <th>Destination</th>
                <th>Payable estimate</th>
                <th>Status</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {list.map((order) => {
                const party = order.viewerRole === "buyer" ? order.supplier : order.buyer;
                return (
                  <tr key={order.id} className={order.id === selected?.id ? "is-selected" : undefined} onClick={() => setSearchParams({ id: order.id })}>
                    <td><strong>{order.orderNumber}</strong><small>{order.negotiation.negotiationNumber}</small></td>
                    <td><strong>{order.product.name}</strong><small>{order.product.productCode}</small></td>
                    <td>{Number(order.quantity).toLocaleString("en-IN")} {order.uom.toLowerCase()}</td>
                    <td><strong><OrgLink organisationId={party.organisationId}>{party.organisation}</OrgLink></strong><small>{party.name}</small></td>
                    <td>{order.destinationPin ?? "—"}</td>
                    <td>{formatMoney(order.charges.payable, 2)}</td>
                    <td><OrderStatusBadge status={order.status} /></td>
                    <td>{formatDate(order.updatedAt)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      {data && (
        <div className="tracking-layout">
          <section className="tracking-map"><div className="map-grid"/><div className="route-path"><i className="origin"/><span/><Truck size={24}/><span/><i className="destination"/></div><div className="map-location map-location--a"><strong><OrgLink organisationId={data.supplier.organisationId}>{data.supplier.organisation}</OrgLink></strong><small>{milestone(data, "dispatched", "Not dispatched yet")}</small></div><div className="map-location map-location--b"><strong>{data.buyer.organisation}</strong><small>{milestone(data, "delivered", "Awaiting delivery")}</small></div></section>
          <aside className="shipment-panel">
            <OrderStatusBadge status={data.status} />
            <Heading level={2}>{data.orderNumber}</Heading>
            <p>{data.product.name} · {Number(data.quantity).toLocaleString("en-IN")} {data.uom.toLowerCase()}</p>
            <div className="eta-block"><small>CURRENT STATUS</small><strong>{titleCase(data.status)}</strong><span>Updated {formatDateTime(data.lastUpdatedAt)}{data.viewerRole === "buyer" ? " · updates come from the supplier" : ""}</span></div>
            <ShipmentFacts key={`shipment:${data.orderId}:${data.status}:${data.shipment.lrNumber ?? ""}:${data.shipment.eta ?? ""}`} tracking={data} onChanged={refresh} />
            <StatusAction key={`${data.orderId}:${data.status}`} tracking={data} onChanged={refresh} />
            <OrderTimeline steps={data.steps} />
          </aside>
        </div>
      )}
    </AsyncContent>
  );
}
