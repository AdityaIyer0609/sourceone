import { ChevronRight, Filter, Search } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { paths } from "../../app/paths";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { ProductVisual } from "../../components/product/ProductVisual";
import { RequirementList } from "../../components/product/RequirementList";
import { OrgLink } from "../../components/supplier/OrgLink";
import { Badge, Button, Input, Modal } from "../../components/ui";
import { onSessionChange, readSession } from "../../lib/api/auth";
import { ApiError, getErrorMessage } from "../../lib/api/client";
import { readDeliveryPin } from "../../lib/deliveryPin";
import { OrderTimeline } from "../../components/order/OrderTimeline";
import { cancelOrder, downloadOrderDocument, getOrderTracking, isPlacedOrder, listOrders, placeForAssignment, ORDER_DOCUMENT_TYPES, reviewOrderDocument, uploadOrderDocument, type Order, type OrderStatus } from "../../lib/api/orders";
import { listProducts, selectPricing } from "../../lib/api/products";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { PAYMENT_TERMS, adjustUnitPrice } from "../../lib/paymentTerms";
import { BENCHMARK_GLYPH, formatDate, formatDateTime, formatMoney, orderCharges, previewOrderTotal, titleCase } from "../../lib/pricingFormat";
import { RequestModal } from "./PurchaseRequestsWorkspace";

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
      <div className="modal-product"><ProductVisual glyph={BENCHMARK_GLYPH} /><div><strong>{order.product.name}</strong><small>{order.supplier ? <>{order.buyer.organisation} ↔ <OrgLink organisationId={order.supplier.organisationId}>{order.supplier.organisation}</OrgLink></> : order.buyer.organisation}</small></div><OrderStatusBadge status={order.status} /></div>
      <div className="modal-cost">
        <Row label="Quantity">{quantityText(order.quantity, order.uom)}</Row>
        <Row label="Agreed unit price (negotiated)">{formatMoney(order.agreedPrice.unitPrice, 4)} / {order.uom.toLowerCase()}</Row>
        {order.negotiation && <Row label="Negotiation">{order.negotiation.negotiationNumber} · accepted offer V{order.negotiation.acceptedVersionNumber}</Row>}
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
        {order.negotiation && <Button variant="secondary" onClick={() => navigate(`${paths.negotiations}?id=${encodeURIComponent(order.negotiation?.id ?? "")}`)}>View negotiation</Button>}
        <Button variant="secondary" onClick={() => navigate(`${paths.orderTracking}?id=${encodeURIComponent(order.id)}`)}>Open tracking</Button>
        {order.allowedActions.cancel && <Button disabled={busy} onClick={cancel}>Cancel order</Button>}
      </div>
    </Modal>
  );
}

function PlaceOrderModal({ onClose, onPlaced }: { onClose: () => void; onPlaced: (orderId: string) => void }) {
  const products = useApiQuery("order-products", (signal) => listProducts({}, signal));
  const [code, setCode] = useState("");
  const [amount, setAmount] = useState("1000");
  const [destination, setDestination] = useState(readDeliveryPin);
  const [paymentTerms, setPaymentTerms] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = (products.data ?? []).find((item) => item.productCode === code) ?? null;
  const pinOk = /^[1-9][0-9]{5}$/.test(destination);
  const quantityOk = Number(amount) > 0;
  const price = selected ? selectPricing(selected)?.current?.value ?? null : null;
  const unit = price ? adjustUnitPrice(price.amount, paymentTerms) : "";
  const material = price && quantityOk ? previewOrderTotal(amount, { amount: unit, currency: price.currency }) : null;
  const charges = material ? orderCharges(material, null) : null;
  const place = async () => {
    if (!selected || !pinOk || !quantityOk) return;
    setBusy(true);
    setError(null);
    try {
      const order = await placeForAssignment({
        productCode: selected.productCode,
        quantity: amount,
        destinationPin: destination,
        paymentTerms: paymentTerms || undefined,
      });
      if (!isPlacedOrder(order)) {
        setError("The order was not placed.");
        return;
      }
      onPlaced(order.id);
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open className="modal--wide" title="Place order" onClose={onClose}>
      <div className="form-grid request-form">
        <label>Product
          <select className="field-select" aria-label="Product" value={code} onChange={(event) => setCode(event.target.value)}>
            <option value="">Select a product</option>
            {(products.data ?? []).map((item) => <option key={item.productCode} value={item.productCode}>{item.name}</option>)}
          </select>
        </label>
        <label>Quantity<div className="input-combo"><Input value={amount} onChange={(event) => setAmount(event.target.value)} /><span>{selected?.uom.code ?? "UOM"}</span></div></label>
        <label>Delivery PIN<Input value={destination} onChange={(event) => setDestination(event.target.value)} placeholder="6-digit PIN" /></label>
        <label>Payment terms
          <select className="field-select" aria-label="Payment terms" value={paymentTerms} onChange={(event) => setPaymentTerms(event.target.value)}>
            {PAYMENT_TERMS.map((term) => <option key={term.label} value={term.value}>{term.label}</option>)}
          </select>
        </label>
      </div>
      <p className="request-note">The price is the current average. Advance lowers the material by 1%. Paying up to 14 days late adds 0.25% to 1.5%. Freight is added after the order is accepted. Payable is an estimate.</p>
      {!code ? <p className="request-note">Choose a product first.</p> : !price ? <p className="request-note">This product has no price yet.</p> : !pinOk ? <p className="request-note">Enter a delivery PIN to see the amount payable.</p> : material && charges && (
        <div className="modal-cost">
          <Row label="Current average">{formatMoney({ amount: unit, currency: price.currency }, 4)} / {(selected?.uom.code ?? "KG").toLowerCase()}</Row>
          <Row label="Material">{formatMoney(material, 2)}</Row>
          <Row label="Estimated freight">Added after the order is accepted</Row>
          <Row label="GST estimate">{formatMoney(charges.gst, 2)}</Row>
          <Row label="Amount payable">{formatMoney(charges.payable, 2)}</Row>
        </div>
      )}
      {error && <p className="negative">{error}</p>}
      <div className="modal-actions">
        <Button variant="secondary" onClick={onClose}>Close</Button>
        <Button disabled={busy || !selected || !pinOk || !quantityOk || !price} onClick={() => void place()}>{busy ? "Placing…" : "Place order"}</Button>
      </div>
    </Modal>
  );
}

export function OrdersWorkspace() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [session, setSession] = useState(readSession);
  useEffect(() => onSessionChange(() => setSession(readSession())), []);
  const buyer = session?.user.roles.includes("buyer") ?? false;
  const hideSuppliers = session?.user.hideSuppliers === true;
  const { data: orders = [], error, isLoading, reload } = useApiQuery("orders", (signal) => listOrders(signal));
  const creating = searchParams.get("new") === "1";
  const selected = creating ? null : orders.find((order) => order.id === searchParams.get("id")) ?? null;
  const count = (...statuses: OrderStatus[]) => orders.filter((order) => statuses.includes(order.status)).length;
  const term = search.trim().toLowerCase();
  const rows = orders.filter((order) =>
    [order.orderNumber, order.product.name, order.negotiation?.negotiationNumber, order.status].join(" ").toLowerCase().includes(term),
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
        <div className="data-toolbar"><label className="search-box search-box--small"><Search size={17}/><Input placeholder="Search orders…" value={search} onChange={(event) => setSearch(event.target.value)}/></label><div>{buyer && <Button onClick={() => setSearchParams({ new: "1" })}>New order</Button>}<Button variant="secondary" {...unavailable}><Filter size={16}/> Filter</Button><Button variant="secondary" {...unavailable}>Export</Button></div></div>
        <AsyncContent isLoading={isLoading && !orders.length} error={error} onRetry={reload} isEmpty={!orders.length} emptyTitle="No orders yet" emptyMessage={hideSuppliers ? "Place an order for a product. Freight is added after it is accepted." : "Orders are created from an accepted negotiation."} loadingLabel="Loading orders…">
          <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Reference</th><th>Material / description</th><th>Quantity</th><th>Value / rate</th><th>Status</th><th>Date</th><th/></tr></thead><tbody>{rows.map((order) => (
            <tr key={order.id} onClick={() => setSearchParams({ id: order.id })} style={{ cursor: "pointer" }}>
              <td><strong>{order.orderNumber}</strong>{order.negotiation && <small>{order.negotiation.negotiationNumber}</small>}</td>
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
      {creating && hideSuppliers && <PlaceOrderModal onClose={() => setSearchParams({})} onPlaced={(orderId) => { reload(); setSearchParams({ id: orderId }); }} />}
      {creating && !hideSuppliers && (
        <RequestModal
          productCode=""
          quantity=""
          pin={readDeliveryPin()}
          price=""
          onClose={() => setSearchParams({})}
          onCreated={reload}
        />
      )}
    </>
  );
}
