import { Search } from "lucide-react";
import { Fragment, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { paths } from "../../app/paths";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { CreateOrderModal } from "../../components/negotiation/CreateOrderModal";
import { RequirementList } from "../../components/product/RequirementList";
import { OrgLink } from "../../components/supplier/OrgLink";
import { Badge, Button, Input, Modal } from "../../components/ui";
import { readSession } from "../../lib/api/auth";
import { readDeliveryPin } from "../../lib/deliveryPin";
import { getErrorMessage } from "../../lib/api/client";
import { listSupplierMatches } from "../../lib/api/listings";
import { listProducts } from "../../lib/api/products";
import { getNegotiation, type Negotiation } from "../../lib/api/negotiations";
import { cancelPurchaseRequest, createPurchaseRequest, listPurchaseRequests, sendPurchaseRequest, type PurchaseRequest } from "../../lib/api/purchaseRequests";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatMoney, formatSignedMoney, titleCase } from "../../lib/pricingFormat";

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
  const [destination, setDestination] = useState(pin || readDeliveryPin());
  const [message, setMessage] = useState("");
  const [requiredBy, setRequiredBy] = useState("");
  const [paymentTerms, setPaymentTerms] = useState("");
  const [freightBasis, setFreightBasis] = useState<"standard" | "distance">("standard");
  const [supplierIds, setSupplierIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = (products.data ?? []).find((item) => item.productCode === code) ?? null;
  const pinOk = /^[1-9][0-9]{5}$/.test(destination);
  const quantityOk = Number(amount) > 0;
  const matches = useApiQuery(
    code && selected && pinOk && quantityOk ? `rfq-matches:${code}:${amount}:${destination}` : null,
    (signal) => listSupplierMatches(code, { quantity: amount, uom: selected?.uom.code ?? "KG", destinationPin: destination }, signal),
  );
  const chosen = (matches.data?.matches ?? []).filter((item) => supplierIds.includes(item.supplierUserId));
  const toggleSupplier = (id: string) => setSupplierIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
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
        freightBasis,
        requiredBy: requiredBy || undefined,
        paymentTerms: paymentTerms || undefined,
        message: message.trim() || undefined,
        supplierUserIds: supplierIds,
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
      <div className="form-grid request-form">
        <label>Product
          <select className="field-select" aria-label="Product" value={code} onChange={(event) => { setCode(event.target.value); setSupplierIds([]); }}>
            <option value="">Select a product</option>
            {(products.data ?? []).map((item) => <option key={item.productCode} value={item.productCode}>{item.name}</option>)}
          </select>
        </label>
        <label>Quantity<div className="input-combo"><Input value={amount} onChange={(event) => setAmount(event.target.value)} /><span>{selected?.uom.code ?? "UOM"}</span></div></label>
        <label>Delivery PIN<Input value={destination} onChange={(event) => setDestination(event.target.value)} placeholder="6-digit PIN" /></label>
        <label>Required by<Input type="date" aria-label="Required by" value={requiredBy} onChange={(event) => setRequiredBy(event.target.value)} /></label>
        <label>Payment terms
          <select className="field-select" aria-label="Payment terms" value={paymentTerms} onChange={(event) => setPaymentTerms(event.target.value)}>
            <option value="">Not specified</option>
            <option value="Advance">Advance</option>
            <option value="30 days">30 days</option>
            <option value="45 days">45 days</option>
            <option value="Letter of credit">Letter of credit</option>
          </select>
        </label>
        <label>Freight basis
          <select className="field-select" aria-label="Freight basis" value={freightBasis} onChange={(event) => setFreightBasis(event.target.value as "standard" | "distance")}>
            <option value="standard">Normal freight</option>
            <option value="distance">Road distance</option>
          </select>
        </label>
        <div className="form-grid__wide">
          <span className="match-label">Suppliers</span>
          {!code ? <p className="request-note">Choose a product first.</p> : !pinOk ? <p className="request-note">Enter a delivery PIN to match suppliers.</p> : matches.isLoading ? <p className="request-note">Matching suppliers…</p> : (
            <ul className="match-pick">{(matches.data?.matches ?? []).map((match) => (
              <li key={match.supplierUserId}>
                <label>
                  <input type="checkbox" checked={supplierIds.includes(match.supplierUserId)} disabled={!match.meetsMinimum} onChange={() => toggleSupplier(match.supplierUserId)} />
                  {match.organisation.replace(/\s*\(demo supplier\)\s*$/i, "")} · {match.supplierName} · {formatMoney(match.askingPrice)} · {match.meetsMinimum ? "Minimum met" : "Below minimum"}
                </label>
              </li>
            ))}</ul>
          )}
        </div>
        <label className="form-grid__wide">Message<Input value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Optional note to the supplier" /></label>
      </div>
      <p className="request-note">Sending asks the selected supplier through a negotiation at their current asking price. Freight stays an estimate, and no order is created.</p>
      {chosen.map((match) => <ul key={match.supplierUserId} className="match-reasons">{match.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>)}
      {matches.data && matches.data.matches.length === 0 && <p className="request-note">No supplier is listing this product.</p>}
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
  const buyer = readSession()?.user.roles.includes("buyer") ?? false;
  const [creating, setCreating] = useState(buyer && Boolean(searchParams.get("product")));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [placing, setPlacing] = useState<Negotiation | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: requests = [], error: loadError, isLoading, reload } = useApiQuery("purchase-requests", (signal) => listPurchaseRequests(signal));
  const term = search.trim().toLowerCase();
  const rows = requests.filter((request) =>
    [request.requestNumber, request.productName, request.productCode, request.status, ...request.suppliers.map((supplier) => supplier.organisation)].join(" ").toLowerCase().includes(term),
  );
  const count = (status: PurchaseRequest["status"]) => requests.filter((request) => request.status === status).length;
  const selected = rows.find((request) => request.id === selectedId) ?? null;
  const placeOrder = async (negotiationId: string) => {
    setError(null);
    try {
      setPlacing(await getNegotiation(negotiationId));
    } catch (cause) {
      setError(getErrorMessage(cause));
    }
  };
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
          {buyer && <Button onClick={() => setCreating(true)}>New request</Button>}
        </div>
        {error && <p className="negative">{error}</p>}
        <AsyncContent isLoading={isLoading && !requests.length} error={loadError} onRetry={reload} isEmpty={!requests.length} emptyTitle="No purchase requests" emptyMessage="Create a request for an active product. Sending it opens a negotiation." loadingLabel="Loading purchase requests…">
          <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Request</th><th>Product</th><th>Quantity</th><th>Destination</th><th>Supplier</th><th>Freight</th><th>Status</th><th/></tr></thead><tbody>{rows.map((request) => {
            const supplier = request.suppliers[0];
            const several = request.suppliers.length > 1;
            const open = selected?.id === request.id;
            return (
              <Fragment key={request.id}>
                <tr onClick={() => setSelectedId(open ? null : request.id)} style={{ cursor: "pointer" }}>
                  <td><strong>{request.requestNumber}</strong><small>{request.buyerOrganisation}</small></td>
                  <td><strong>{request.productName}</strong><small>{request.productCode}</small></td>
                  <td>{Number(request.quantity).toLocaleString("en-IN")} {request.uom.toLowerCase()}</td>
                  <td>{request.destinationPin}</td>
                  <td>{several ? <strong>{request.suppliers.length} suppliers</strong> : supplier ? <><strong><OrgLink organisationId={supplier.organisationId}>{supplier.organisation}</OrgLink></strong><small>{supplier.supplierName}</small></> : <small>Not selected</small>}</td>
                  <td>{several ? "Per supplier" : freightText(request)}</td>
                  <td><Badge tone={STATUS_TONE[request.status]}>{titleCase(request.status)}</Badge></td>
                  <td onClick={(event) => event.stopPropagation()}>
                    {request.canSend && <Button disabled={busyId === request.id} onClick={() => void act(request.id, "send")}>Send</Button>}
                    {!several && supplier?.negotiationId && <Button variant="secondary" onClick={() => navigate(`${paths.negotiations}?id=${encodeURIComponent(supplier.negotiationId ?? "")}`)}>Open negotiation</Button>}
                    {several && <small>{open ? "Negotiations are open below" : "Expand to engage in negotiations"}</small>}
                    {request.canCancel && <Button variant="ghost" disabled={busyId === request.id} onClick={() => void act(request.id, "cancel")}>Cancel</Button>}
                  </td>
                </tr>
                {open && request.suppliers.length > 0 && (
                  <tr>
                    <td colSpan={8}>
                      <div className="data-toolbar">
                        <strong>{request.requestNumber}</strong>
                        <small>{request.requiredBy ? `Required by ${request.requiredBy}` : "No required date"}{request.paymentTerms ? ` · ${request.paymentTerms}` : ""} · PIN {request.destinationPin}</small>
                      </div>
                      {request.requirements && request.requirements.length > 0 && <RequirementList rows={request.requirements} />}
                      <table className="market-table"><thead><tr><th>Supplier</th><th>Asking price</th><th>Latest offer</th><th>Material</th><th>Freight</th><th>GST</th><th>Payable estimate</th><th>Status</th><th/></tr></thead><tbody>
                        {request.suppliers.map((row) => (
                          <tr key={row.supplierUserId}>
                            <td><strong><OrgLink organisationId={row.organisationId}>{row.organisation}</OrgLink></strong><small>{row.supplierName}</small></td>
                            <td>{row.askingPrice ? formatMoney(row.askingPrice) : "—"}</td>
                            <td>{row.latestOffer ? formatMoney(row.latestOffer) : "—"}{row.quote.versusSnapshot && <small>{formatSignedMoney(row.quote.versusSnapshot)} vs snapshot</small>}{row.quote.versusAverage && <small>{formatSignedMoney(row.quote.versusAverage)} vs average</small>}</td>
                            <td>{row.materialValue ? formatMoney(row.materialValue, 2) : "—"}</td>
                            <td>{row.freightStatus === "estimated" && row.freight ? formatMoney(row.freight) : "On request"}</td>
                            <td>{row.charges ? formatMoney(row.charges.gst, 2) : "—"}</td>
                            <td>{row.charges ? formatMoney(row.charges.payable, 2) : "—"}</td>
                            <td>{row.negotiationStatus ? titleCase(row.negotiationStatus) : "Not sent"}</td>
                            <td>
                              {row.negotiationId && <Button variant="secondary" onClick={() => navigate(`${paths.negotiations}?id=${encodeURIComponent(row.negotiationId ?? "")}`)}>Open negotiation</Button>}
                              {buyer && row.negotiationStatus === "accepted" && row.negotiationId && <Button onClick={() => void placeOrder(row.negotiationId ?? "")}>Place order</Button>}
                            </td>
                          </tr>
                        ))}
                      </tbody></table>
                      <p className="request-note">{request.suppliers.find((row) => row.charges)?.charges?.gstBasis ?? "GST is shown only when a material offer exists."} Payable is an estimate. The negotiated price and the order total stay the material value.</p>
                    </td>
                  </tr>
                )}
              </Fragment>
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
      {placing && (
        <CreateOrderModal
          negotiation={placing}
          onClose={() => setPlacing(null)}
          onCreated={() => { setPlacing(null); reload(); }}
          onViewOrder={(order) => navigate(`${paths.orders}?id=${encodeURIComponent(order.id)}`)}
        />
      )}
    </>
  );
}
