import { ChevronRight, Filter, Search } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { paths } from "../../app/paths";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { ProductVisual } from "../../components/product/ProductVisual";
import { RequirementList } from "../../components/product/RequirementList";
import { OrgLink } from "../../components/supplier/OrgLink";
import { Badge, Button, Input, Modal } from "../../components/ui";
import { ApiError, getErrorMessage } from "../../lib/api/client";
import { OrderTimeline } from "../../components/order/OrderTimeline";
import { cancelOrder, downloadOrderDocument, getOrderTracking, listOrders, ORDER_DOCUMENT_TYPES, reviewOrderDocument, uploadOrderDocument, type Order, type OrderStatus } from "../../lib/api/orders";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { BENCHMARK_GLYPH, formatDate, formatDateTime, formatMoney, titleCase } from "../../lib/pricingFormat";

const STATUS_TONES: Record<OrderStatus, "neutral" | "positive" | "warning" | "negative" | "info"> = {
  placed: "info",
  confirmed: "info",
  processing: "warning",
  ready: "warning",
  dispatched: "warning",
  in_transit: "warning",
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
  const [documentType, setDocumentType] = useState<string>(ORDER_DOCUMENT_TYPES[0][0]);
  const [uploadName, setUploadName] = useState("");
  const freightKnown = order.freightStatus === "estimated" && order.freight ? order.freight : null;
  return (
    <Modal open className="modal--wide" title={`Order ${order.orderNumber}`} onClose={onClose}>
      <div className="modal-product"><ProductVisual glyph={BENCHMARK_GLYPH} /><div><strong>{order.product.name}</strong><small>{order.buyer.organisation} ↔ <OrgLink organisationId={order.supplier.organisationId}>{order.supplier.organisation}</OrgLink></small></div><OrderStatusBadge status={order.status} /></div>
      <div className="modal-cost">
        <Row label="Quantity">{quantityText(order.quantity, order.uom)}</Row>
        <Row label="Agreed unit price (negotiated)">{formatMoney(order.agreedPrice.unitPrice, 4)} / {order.uom.toLowerCase()}</Row>
        <Row label="Negotiation">{order.negotiation.negotiationNumber} · accepted offer V{order.negotiation.acceptedVersionNumber}</Row>
        <Row label="Placed">{formatDateTime(order.createdAt)}</Row>
        {order.cancelledAt && <Row label="Cancelled">{formatDateTime(order.cancelledAt)}{order.cancelReason ? ` · ${order.cancelReason}` : ""}</Row>}
        <Row label="Delivery PIN">{order.destinationPin ?? "—"}</Row>
        {tracking.data && <Row label="LR">{tracking.data.shipment.lrNumber ?? "No LR saved."}</Row>}
        {tracking.data && <Row label="ETA">{tracking.data.shipment.eta ? formatDate(tracking.data.shipment.eta) : "No ETA saved."}</Row>}
        {tracking.data && <Row label="Delay">{tracking.data.delayed ? `Past the required date of ${formatDate(tracking.data.requiredBy ?? "")}.` : tracking.data.requiredBy ? `Required by ${formatDate(tracking.data.requiredBy)}.` : "No required date is stored, so a delay is not shown."}</Row>}
        <Row label="Material (negotiated)">{formatMoney(order.totalValue, 2)}</Row>
        <Row label="Estimated freight">{freightKnown ? formatMoney(freightKnown) : order.freightStatus === "on_request" ? "Freight on request" : "—"}</Row>
        <Row label="GST estimate">{formatMoney(order.charges.gst, 2)}</Row>
        <Row label="Amount payable">{formatMoney(order.charges.payable, 2)}</Row>
      </div>
      {order.requirements.length > 0 && <RequirementList rows={order.requirements} />}
      <div className="spec-grid">
        {order.documents.map((document) => (
          <div key={document.id}>
            <small>{ORDER_DOCUMENT_TYPES.find((item) => item[0] === document.documentType)?.[1] ?? document.documentType} · {titleCase(document.status)}</small>
            <strong>{document.filename}</strong>
            <Button variant="ghost" onClick={() => void downloadOrderDocument(order.id, document.id, document.filename).catch((cause) => setError(cause))}>Download</Button>
            {order.viewerRole === "buyer" && document.status === "submitted" && <Button variant="ghost" disabled={busy} onClick={() => void reviewOrderDocument(order.id, document.id, "accepted").then(onChanged).catch((cause) => setError(cause))}>Accept</Button>}
            {order.viewerRole === "buyer" && document.status === "submitted" && <Button variant="ghost" disabled={busy} onClick={() => void reviewOrderDocument(order.id, document.id, "rejected").then(onChanged).catch((cause) => setError(cause))}>Reject</Button>}
          </div>
        ))}
      </div>
      {(order.documents.length === 0 || (order.viewerRole === "supplier" && order.status !== "cancelled")) && (
        <div className="doc-upload">
          {order.documents.length === 0 && <p className="request-note">No fulfilment documents have been uploaded.</p>}
          {order.viewerRole === "supplier" && order.status !== "cancelled" && (
            <div className="form-grid">
              <label>Document type
                <select className="field-select" aria-label="Document type" value={documentType} disabled={busy} onChange={(event) => setDocumentType(event.target.value)}>
                  {ORDER_DOCUMENT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              <label>File
                <span className="file-field">
                  <input className="file-field__input" aria-label="Fulfilment file" type="file" disabled={busy} onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (!file) return;
                    setUploadName(file.name);
                    setBusy(true);
                    setError(null);
                    uploadOrderDocument(order.id, documentType, file).then(onChanged).catch((cause) => setError(cause)).finally(() => { setBusy(false); setUploadName(""); });
                  }} />
                  <span className="file-field__button">{busy ? "Uploading" : "Choose file"}</span>
                  <span className="file-field__name">{busy && uploadName ? uploadName : "No file chosen"}</span>
                </span>
              </label>
            </div>
          )}
        </div>
      )}
      {tracking.data ? <OrderTimeline steps={tracking.data.steps} /> : tracking.error ? <p className="negative" role="alert">{getErrorMessage(tracking.error)}</p> : null}
      {error ? <p className="negative" role="alert">{getErrorMessage(error)}{error instanceof ApiError && error.code ? ` (${error.code})` : ""}</p> : null}
      <div className="modal-actions modal-actions--order">
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
          ["IN PROGRESS", count("processing", "ready", "dispatched", "in_transit"), "Processing through transit"],
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
              <td><strong>{formatMoney(order.charges.payable, 2)}</strong><small>@ {formatMoney(order.agreedPrice.unitPrice)} / {order.uom.toLowerCase()} · incl. freight & GST</small></td>
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
