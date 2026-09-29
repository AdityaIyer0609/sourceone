import { Search } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { paths } from "../../app/paths";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Badge, Button, Input, Modal } from "../../components/ui";
import { getErrorMessage } from "../../lib/api/client";
import { listProductListings } from "../../lib/api/listings";
import { listProducts } from "../../lib/api/products";
import { cancelPurchaseRequest, createPurchaseRequest, listPurchaseRequests, sendPurchaseRequest, type PurchaseRequest } from "../../lib/api/purchaseRequests";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatMoney, titleCase } from "../../lib/pricingFormat";

const STATUS_TONE = { draft: "neutral", sent: "info", in_negotiation: "warning", converted: "positive", cancelled: "negative" } as const;

function freightText(request: PurchaseRequest) {
  const row = request.suppliers[0];
  if (!row) return "Choose a supplier";
  if (row.freightStatus === "estimated" && row.freight) return formatMoney(row.freight);
  return "Freight on request";
}

function RequestModal({ productCode, quantity, pin, onClose, onCreated }: {
  productCode: string;
  quantity: string;
  pin: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const products = useApiQuery("rfq-products", (signal) => listProducts({}, signal));
  const [code, setCode] = useState(productCode);
  const [amount, setAmount] = useState(quantity || "1000");
  const [destination, setDestination] = useState(pin);
  const [message, setMessage] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = (products.data ?? []).find((item) => item.productCode === code) ?? null;
  const listings = useApiQuery(code ? `rfq-listings:${code}` : null, (signal) => listProductListings(code, undefined, signal));
  const pinOk = /^[1-9][0-9]{5}$/.test(destination);
  const submit = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await createPurchaseRequest({
        productCode: selected.productCode,
        quantity: amount,
        uom: selected.uom.code,
        destinationPin: destination,
        message: message.trim() || undefined,
        supplierUserIds: supplierId ? [supplierId] : [],
      });
      onCreated();
      onClose();
    } catch (cause) {
      setError(getErrorMessage(cause));
      setBusy(false);
    }
  };
  return (
    <Modal open title="Create purchase request" onClose={onClose}>
      <div className="form-grid">
        <label>Product
          <select value={code} onChange={(event) => { setCode(event.target.value); setSupplierId(""); }}>
            <option value="">Select a product</option>
            {(products.data ?? []).map((item) => <option key={item.productCode} value={item.productCode}>{item.productCode} · {item.name}</option>)}
          </select>
        </label>
        <label>Quantity<div className="input-combo"><Input value={amount} onChange={(event) => setAmount(event.target.value)} /><span>{selected?.uom.code ?? "UOM"}</span></div></label>
        <label>Delivery PIN<Input value={destination} onChange={(event) => setDestination(event.target.value)} /></label>
        <label>Supplier
          <select value={supplierId} onChange={(event) => setSupplierId(event.target.value)}>
            <option value="">Select later</option>
            {(listings.data ?? []).map((listing) => <option key={listing.supplierUserId} value={listing.supplierUserId}>{listing.organisation} · {listing.supplierName}</option>)}
          </select>
        </label>
        <label>Message<Input value={message} onChange={(event) => setMessage(event.target.value)} /></label>
      </div>
      <p><small>Sending asks the selected supplier through a negotiation at their current asking price. Freight stays an estimate, and no order is created.</small></p>
      {error && <p className="negative">{error}</p>}
      <div className="modal-actions">
        <Button variant="secondary" onClick={onClose}>Close</Button>
        <Button disabled={!selected || !(Number(amount) > 0) || !pinOk || busy} onClick={() => void submit()}>{busy ? "Saving…" : "Save draft"}</Button>
      </div>
    </Modal>
  );
}

export function PurchaseRequestsWorkspace() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(Boolean(searchParams.get("product")));
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: requests = [], error: loadError, isLoading, reload } = useApiQuery("purchase-requests", (signal) => listPurchaseRequests(signal));
  const term = search.trim().toLowerCase();
  const rows = requests.filter((request) =>
    [request.requestNumber, request.productName, request.productCode, request.status, ...request.suppliers.map((supplier) => supplier.organisation)].join(" ").toLowerCase().includes(term),
  );
  const count = (status: PurchaseRequest["status"]) => requests.filter((request) => request.status === status).length;
  const act = async (id: string, action: "send" | "cancel") => {
    setBusyId(id);
    setError(null);
    try {
      if (action === "send") await sendPurchaseRequest(id);
      else await cancelPurchaseRequest(id);
      reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusyId(null);
    }
  };
  return (
    <>
      <div className="metric-row">
        {[
          ["DRAFT", count("draft"), "Not sent"],
          ["SENT", count("sent"), "Waiting on the supplier"],
          ["IN NEGOTIATION", count("in_negotiation"), "Supplier has responded"],
          ["CONVERTED", count("converted"), "Order placed from the negotiation"],
        ].map(([label, value, note]) => <div key={label}><small>{label}</small><strong>{String(value).padStart(2, "0")}</strong><span>{note}</span></div>)}
      </div>
      <section className="section-block data-section">
        <div className="data-toolbar">
          <label className="search-box search-box--small"><Search size={17}/><Input placeholder="Search purchase requests…" value={search} onChange={(event) => setSearch(event.target.value)}/></label>
          <Button onClick={() => setCreating(true)}>New request</Button>
        </div>
        {error && <p className="negative">{error}</p>}
        <AsyncContent isLoading={isLoading && !requests.length} error={loadError} onRetry={reload} isEmpty={!requests.length} emptyTitle="No purchase requests" emptyMessage="Create a request for an active product. Sending it opens a negotiation." loadingLabel="Loading purchase requests…">
          <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Request</th><th>Product</th><th>Quantity</th><th>Destination</th><th>Supplier</th><th>Freight</th><th>Status</th><th/></tr></thead><tbody>{rows.map((request) => {
            const supplier = request.suppliers[0];
            return (
              <tr key={request.id}>
                <td><strong>{request.requestNumber}</strong><small>{request.buyerOrganisation}</small></td>
                <td><strong>{request.productName}</strong><small>{request.productCode}</small></td>
                <td>{Number(request.quantity).toLocaleString("en-IN")} {request.uom.toLowerCase()}</td>
                <td>{request.destinationPin}</td>
                <td>{supplier ? <><strong>{supplier.organisation}</strong><small>{supplier.supplierName}</small></> : <small>Not selected</small>}</td>
                <td>{freightText(request)}</td>
                <td><Badge tone={STATUS_TONE[request.status]}>{titleCase(request.status)}</Badge></td>
                <td>
                  {request.canSend && <Button disabled={busyId === request.id} onClick={() => void act(request.id, "send")}>Send</Button>}
                  {supplier?.negotiationId && <Button variant="secondary" onClick={() => navigate(`${paths.negotiations}?id=${encodeURIComponent(supplier.negotiationId ?? "")}`)}>Open negotiation</Button>}
                  {request.canCancel && <Button variant="ghost" disabled={busyId === request.id} onClick={() => void act(request.id, "cancel")}>Cancel</Button>}
                </td>
              </tr>
            );
          })}</tbody></table></div>
        </AsyncContent>
      </section>
      {creating && (
        <RequestModal
          productCode={searchParams.get("product") ?? ""}
          quantity={searchParams.get("quantity") ?? ""}
          pin={searchParams.get("pin") ?? ""}
          onClose={() => setCreating(false)}
          onCreated={reload}
        />
      )}
    </>
  );
}
