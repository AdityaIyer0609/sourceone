import { Search } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { paths } from "../../app/paths";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { OrgLink } from "../../components/supplier/OrgLink";
import { Badge, Button, Input, Modal } from "../../components/ui";
import { getErrorMessage } from "../../lib/api/client";
import { readDeliveryPin } from "../../lib/deliveryPin";
import { estimateFreight, shownFreight, type FreightBasis, type FreightEstimate } from "../../lib/api/freight";
import { listReorders, startReorder, type ReorderItem } from "../../lib/api/orders";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatDate, formatMoney, titleCase } from "../../lib/pricingFormat";

const BLOCK_LABEL: Record<string, string> = {
  cancelled: "Cancelled orders are not reordered",
  inactive_product: "This product is no longer available",
  inactive_supplier: "This supplier is no longer available",
  no_listing: "This supplier is not listing the product",
};

function quantityText(quantity: string, uom: string) {
  return `${Number(quantity).toLocaleString("en-IN")} ${uom.toLowerCase()}`;
}

function ReorderModal({ item, onClose }: { item: ReorderItem; onClose: () => void }) {
  const navigate = useNavigate();
  const [quantity, setQuantity] = useState(item.quantity);
  const [pin, setPin] = useState(readDeliveryPin);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [basis, setBasis] = useState<FreightBasis>("standard");
  const pinOk = /^[1-9][0-9]{5}$/.test(pin);
  const quantityOk = Number(quantity) > 0;
  const estimate = useApiQuery(
    item.available && pinOk && quantityOk ? `reorder-freight:${item.orderId}:${pin}:${quantity}` : null,
    (signal) => estimateFreight({
      supplierUserId: item.supplierUserId,
      productCode: item.productCode,
      quantity,
      destinationPin: pin,
    }, signal),
  );
  const freightText = (value: FreightEstimate | undefined) => {
    if (!pin) return "Enter a delivery PIN to estimate freight";
    if (!pinOk) return "PIN must be 6 digits";
    if (estimate.error) return getErrorMessage(estimate.error);
    if (!value) return "…";
    const shown = shownFreight(value, basis);
    return shown.status === "estimated" && shown.freight ? formatMoney(shown.freight) : "Freight on request";
  };
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await startReorder(item.orderId, {
        quantity,
        ...(pinOk ? { destinationPin: pin } : {}),
      });
      navigate(`${paths.negotiations}?id=${encodeURIComponent(created.negotiationId)}`);
    } catch (cause) {
      setError(getErrorMessage(cause));
      setBusy(false);
    }
  };
  return (
    <Modal open title={`Reorder ${item.orderNumber}`} onClose={onClose}>
      <div className="modal-cost">
        <span><small>Product</small><strong>{item.productName}</strong></span>
        <span><small>Supplier</small><strong><OrgLink organisationId={item.organisationId}>{item.organisation}</OrgLink> · {item.supplierName}</strong></span>
        <span><small>Previous final price</small><strong>{formatMoney(item.previousPrice, 4)} / {item.uom.toLowerCase()}</strong></span>
        <span><small>Current asking price</small><strong>{item.currentAskingPrice ? `${formatMoney(item.currentAskingPrice, 4)} / ${item.uom.toLowerCase()}` : "—"}</strong></span>
        <span><small>Plenza benchmark</small><strong>{item.currentBenchmark ? formatMoney(item.currentBenchmark, 4) : "Rate on request"}</strong></span>
        <span><small>{estimate.data ? shownFreight(estimate.data, basis).label ?? "Estimated freight" : "Estimated freight"}</small><strong>{freightText(estimate.data)}</strong></span>
      </div>
      {estimate.data && (
        <div className="chip-row" role="group" aria-label="Freight basis">
          <Button variant="ghost" className={`filter-chip${basis === "standard" ? " is-active" : ""}`} onClick={() => setBasis("standard")}>Normal freight</Button>
          <Button variant="ghost" className={`filter-chip${basis === "distance" ? " is-active" : ""}`} onClick={() => setBasis("distance")}>Road distance</Button>
        </div>
      )}
      <div className="form-grid">
        <label>Quantity<div className="input-combo"><Input value={quantity} onChange={(event) => setQuantity(event.target.value)} /><span>{item.uom}</span></div></label>
        <label>Delivery PIN<Input value={pin} placeholder="Change destination" onChange={(event) => setPin(event.target.value)} /></label>
      </div>
      <p><small>The new negotiation opens at the current asking price. The previous order price is not reused, and freight stays an estimate.</small></p>
      {error && <p className="negative">{error}</p>}
      <div className="modal-actions">
        <Button variant="secondary" onClick={onClose}>Close</Button>
        <Button disabled={!item.available || !quantityOk || busy || (pin.length > 0 && !pinOk)} onClick={() => void submit()}>{busy ? "Starting…" : "Reorder"}</Button>
      </div>
    </Modal>
  );
}

export function ReorderWorkspace() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [picked, setPicked] = useState<ReorderItem | null>(null);
  const [closed, setClosed] = useState(false);
  const { data: items = [], error, isLoading, reload } = useApiQuery("reorders", (signal) => listReorders(signal));
  const requested = items.find((item) => item.orderId === searchParams.get("order") && item.available) ?? null;
  const selected = closed ? picked : picked ?? requested;
  const close = () => { setPicked(null); setClosed(true); setSearchParams({}); };
  const term = search.trim().toLowerCase();
  const rows = items.filter((item) =>
    [item.orderNumber, item.productName, item.organisation, item.supplierName, item.orderStatus].join(" ").toLowerCase().includes(term),
  );
  const unavailable = { "aria-disabled": "true" as const, title: "Not available yet" };
  const count = (predicate: (item: ReorderItem) => boolean) => items.filter(predicate).length;
  return (
    <>
      <div className="metric-row">
        {[
          ["REORDERABLE", count((item) => item.available), "Ready to negotiate again"],
          ["UNAVAILABLE", count((item) => !item.available && item.unavailableReason !== "cancelled"), "Product or supplier inactive"],
          ["CANCELLED", count((item) => item.unavailableReason === "cancelled"), "Not reordered"],
          ["PAST ORDERS", items.length, "Your Plenza orders"],
        ].map(([label, value, note]) => <div key={label}><small>{label}</small><strong>{String(value).padStart(2, "0")}</strong><span>{note}</span></div>)}
      </div>
      <section className="section-block data-section">
        <div className="data-toolbar"><label className="search-box search-box--small"><Search size={17}/><Input placeholder="Search past orders…" value={search} onChange={(event) => setSearch(event.target.value)}/></label><div><Button variant="secondary" {...unavailable}>Filter</Button><Button variant="secondary" {...unavailable}>Export</Button></div></div>
        <AsyncContent isLoading={isLoading && !items.length} error={error} onRetry={reload} isEmpty={!items.length} emptyTitle="No past orders" emptyMessage="Completed orders will appear here for reorder." loadingLabel="Loading past orders…">
          <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Order</th><th>Product / supplier</th><th>Previous quantity</th><th>Previous price</th><th>Availability</th><th>Order date</th><th/></tr></thead><tbody>{rows.map((item) => (
            <tr key={item.orderId}>
              <td><strong>{item.orderNumber}</strong><small>{titleCase(item.orderStatus)}</small></td>
              <td><strong>{item.productName}</strong><small><OrgLink organisationId={item.organisationId}>{item.organisation}</OrgLink> · {item.supplierName}</small></td>
              <td>{quantityText(item.quantity, item.uom)}</td>
              <td><strong>{formatMoney(item.previousPrice, 4)}</strong><small>{item.currency} · previous final price</small></td>
              <td>{item.available ? <Badge tone="positive">AVAILABLE</Badge> : <Badge tone={item.unavailableReason === "cancelled" ? "negative" : "warning"}>{item.unavailableReason === "cancelled" ? "CANCELLED" : "UNAVAILABLE"}</Badge>}<small>{item.unavailableReason ? BLOCK_LABEL[item.unavailableReason] : "Current listing"}</small></td>
              <td><small>{formatDate(item.orderedAt)}</small></td>
              <td><Button variant="secondary" disabled={!item.available} title={item.unavailableReason ? BLOCK_LABEL[item.unavailableReason] : undefined} onClick={() => { setClosed(false); setPicked(item); }}>Reorder</Button></td>
            </tr>
          ))}</tbody></table></div>
        </AsyncContent>
      </section>
      {selected && <ReorderModal key={selected.orderId} item={selected} onClose={close} />}
    </>
  );
}
