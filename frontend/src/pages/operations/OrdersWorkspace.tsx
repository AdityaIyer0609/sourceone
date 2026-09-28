import { ChevronRight, Filter, Search } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { paths } from "../../app/paths";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { ProductVisual } from "../../components/product/ProductVisual";
import { Badge, Button, Input, Modal } from "../../components/ui";
import { ApiError, getErrorMessage } from "../../lib/api/client";
import { OrderTimeline } from "../../components/order/OrderTimeline";
import { cancelOrder, getOrderTracking, listOrders, type Order, type OrderStatus } from "../../lib/api/orders";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { BENCHMARK_GLYPH, formatDate, formatDateTime, formatMoney, titleCase } from "../../lib/pricingFormat";

const STATUS_TONES: Record<OrderStatus, "neutral" | "positive" | "warning" | "negative" | "info"> = {
  placed: "info",
  confirmed: "info",
  processing: "warning",
  ready: "warning",
  dispatched: "warning",
  delivered: "positive",
  cancelled: "negative",
};

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  return <Badge tone={STATUS_TONES[status]}>{titleCase(status)}</Badge>;
}

function quantityText(quantity: string, uom: string) {
  return `${Number(quantity).toLocaleString("en-IN")} ${uom.toLowerCase()}`;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return <span><small>{label}</small><strong>{children}</strong></span>;
}

function OrderModal({ order, onClose, onChanged }: { order: Order; onClose: () => void; onChanged: () => void }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const tracking = useApiQuery(`tracking:${order.id}:${order.status}`, (signal) => getOrderTracking(order.id, signal));
  const cancel = async () => {
    setBusy(true);
    setError(null);
    try {
      await cancelOrder(order.id);
      onChanged();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open title={`Order ${order.orderNumber}`} onClose={onClose}>
      <div className="modal-product"><ProductVisual glyph={BENCHMARK_GLYPH} /><div><strong>{order.product.name}</strong><small>{order.buyer.organisation} ↔ {order.supplier.organisation}</small></div><OrderStatusBadge status={order.status} /></div>
      <div className="modal-cost">
        <Row label="Quantity">{quantityText(order.quantity, order.uom)}</Row>
        <Row label="Agreed unit price (negotiated)">{formatMoney(order.agreedPrice.unitPrice, 4)} / {order.uom.toLowerCase()}</Row>
        <Row label="Negotiation">{order.negotiation.negotiationNumber} · accepted offer V{order.negotiation.acceptedVersionNumber}</Row>
        <Row label="Placed">{formatDateTime(order.createdAt)}</Row>
        {order.cancelledAt && <Row label="Cancelled">{formatDateTime(order.cancelledAt)}{order.cancelReason ? ` · ${order.cancelReason}` : ""}</Row>}
        <Row label="Total value">{formatMoney(order.totalValue, 2)}</Row>
      </div>
      {tracking.data ? <OrderTimeline steps={tracking.data.steps} /> : tracking.error ? <p className="negative" role="alert">{getErrorMessage(tracking.error)}</p> : null}
      {error ? <p className="negative" role="alert">{getErrorMessage(error)}{error instanceof ApiError && error.code ? ` (${error.code})` : ""}</p> : null}
      <div className="modal-actions">
        <Button variant="secondary" onClick={onClose}>Close</Button>
        <Button variant="secondary" onClick={() => navigate(`${paths.negotiations}?id=${encodeURIComponent(order.negotiation.id)}`)}>View negotiation</Button>
        <Button variant="secondary" onClick={() => navigate(`${paths.orderTracking}?id=${encodeURIComponent(order.id)}`)}>Open tracking</Button>
        {order.allowedActions.cancel && <Button disabled={busy} onClick={cancel}>Cancel order</Button>}
      </div>
    </Modal>
  );
}

export function OrdersWorkspace() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const { data: orders = [], error, isLoading, reload } = useApiQuery("orders", (signal) => listOrders(signal));
  const selected = orders.find((order) => order.id === searchParams.get("id")) ?? null;
  const count = (...statuses: OrderStatus[]) => orders.filter((order) => statuses.includes(order.status)).length;
  const term = search.trim().toLowerCase();
  const rows = orders.filter((order) =>
    [order.orderNumber, order.product.name, order.negotiation.negotiationNumber, order.status].join(" ").toLowerCase().includes(term),
  );
  const unavailable = { "aria-disabled": "true" as const, title: "Not available yet" };

  return (
    <>
      <div className="metric-row">
        {[
          ["OPEN", count("placed", "confirmed"), "Placed or confirmed"],
          ["IN PROGRESS", count("processing", "ready", "dispatched"), "Processing to dispatch"],
          ["COMPLETED", count("delivered"), "Delivered"],
          ["CANCELLED", count("cancelled"), "Cancelled orders"],
        ].map(([a, b, c]) => <div key={a}><small>{a}</small><strong>{String(b).padStart(2, "0")}</strong><span>{c}</span></div>)}
      </div>
      <section className="section-block data-section">
        <div className="data-toolbar"><label className="search-box search-box--small"><Search size={17}/><Input placeholder="Search orders…" value={search} onChange={(event) => setSearch(event.target.value)}/></label><div><Button variant="secondary" {...unavailable}><Filter size={16}/> Filter</Button><Button variant="secondary" {...unavailable}>Export</Button></div></div>
        <AsyncContent isLoading={isLoading && !orders.length} error={error} onRetry={reload} isEmpty={!orders.length} emptyTitle="No orders yet" emptyMessage="Orders are created from an accepted negotiation." loadingLabel="Loading orders…">
          <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Reference</th><th>Material / description</th><th>Quantity</th><th>Value / rate</th><th>Status</th><th>Date</th><th/></tr></thead><tbody>{rows.map((order) => (
            <tr key={order.id} onClick={() => setSearchParams({ id: order.id })} style={{ cursor: "pointer" }}>
              <td><strong>{order.orderNumber}</strong><small>{order.negotiation.negotiationNumber}</small></td>
              <td><strong>{order.product.name}</strong><small>{titleCase(order.product.category)}</small></td>
              <td>{quantityText(order.quantity, order.uom)}</td>
              <td><strong>{formatMoney(order.totalValue, 2)}</strong><small>@ {formatMoney(order.agreedPrice.unitPrice)} / {order.uom.toLowerCase()}</small></td>
              <td><OrderStatusBadge status={order.status} /></td>
              <td><small>{formatDate(order.createdAt)}</small></td>
              <td><ChevronRight size={16}/></td>
            </tr>
          ))}</tbody></table></div>
        </AsyncContent>
      </section>
      {selected && <OrderModal order={selected} onClose={() => setSearchParams({})} onChanged={reload} />}
    </>
  );
}
