import { Truck } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { OrderTimeline } from "../../components/order/OrderTimeline";
import { Button, Heading, Input } from "../../components/ui";
import { ApiError, getErrorMessage } from "../../lib/api/client";
import { changeOrderStatus, getOrderTracking, listOrders, type OrderTracking } from "../../lib/api/orders";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatDateTime, titleCase } from "../../lib/pricingFormat";
import { OrderStatusBadge } from "./OrdersWorkspace";

function milestone(tracking: OrderTracking, status: "dispatched" | "delivered", pending: string) {
  const at = tracking.steps.find((step) => step.status === status)?.at;
  return at ? `${titleCase(status)} · ${formatDateTime(at)}` : pending;
}

function StatusAction({ tracking, onChanged }: { tracking: OrderTracking; onChanged: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const next = tracking.nextStatus;
  if (!tracking.canProgress || !next) return null;
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await changeOrderStatus(tracking.orderId, next, note.trim());
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
      <Input placeholder="Note for the buyer (optional)" value={note} maxLength={2000} onChange={(event) => setNote(event.target.value)} />
      {error ? <p className="negative" role="alert">{getErrorMessage(error)}{error instanceof ApiError && error.code ? ` (${error.code})` : ""}</p> : null}
      <Button disabled={busy} onClick={submit}>Mark as {titleCase(next)}</Button>
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
      {list.length > 1 && (
        <div className="chip-row">
          {list.map((order) => <Button key={order.id} variant="ghost" className={`filter-chip ${order.id === selected?.id ? "is-active" : ""}`} onClick={() => setSearchParams({ id: order.id })}>{order.orderNumber} · {titleCase(order.status)}</Button>)}
        </div>
      )}
      {data && (
        <div className="tracking-layout">
          <section className="tracking-map"><div className="map-grid"/><div className="route-path"><i className="origin"/><span/><Truck size={24}/><span/><i className="destination"/></div><div className="map-location map-location--a"><strong>{data.supplier.organisation}</strong><small>{milestone(data, "dispatched", "Not dispatched yet")}</small></div><div className="map-location map-location--b"><strong>{data.buyer.organisation}</strong><small>{milestone(data, "delivered", "Awaiting delivery")}</small></div></section>
          <aside className="shipment-panel">
            <OrderStatusBadge status={data.status} />
            <Heading level={2}>{data.orderNumber}</Heading>
            <p>{data.product.name} · {Number(data.quantity).toLocaleString("en-IN")} {data.uom.toLowerCase()}</p>
            <div className="eta-block"><small>CURRENT STATUS</small><strong>{titleCase(data.status)}</strong><span>Updated {formatDateTime(data.lastUpdatedAt)}{data.viewerRole === "buyer" ? " · updates come from the supplier" : ""}</span></div>
            <StatusAction key={`${data.orderId}:${data.status}`} tracking={data} onChanged={refresh} />
            <OrderTimeline steps={data.steps} />
          </aside>
        </div>
      )}
    </AsyncContent>
  );
}
