import { Search } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
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
import { isPlacedOrder, placeAtAsking } from "../../lib/api/orders";
import { cancelPurchaseRequest, cancelRequestSupplier, createPurchaseRequest, listPurchaseRequests, placeRequestSupplier, sendPurchaseRequest, sendRequestSupplier, type PurchaseRequest, type RequestSupplier } from "../../lib/api/purchaseRequests";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { PAYMENT_TERMS, adjustUnitPrice } from "../../lib/paymentTerms";
import { formatMoney, formatSignedMoney, orderCharges, previewOrderTotal, titleCase } from "../../lib/pricingFormat";
import { tradeDecision } from "../../lib/tradeDecision";

const STATUS_TONE = { draft: "neutral", sent: "info", in_negotiation: "warning", converted: "positive", cancelled: "negative" } as const;

function headlineStatus(request: PurchaseRequest): PurchaseRequest["status"] {
  const talks = request.suppliers.map((row) => row.negotiationStatus).filter((status): status is string => Boolean(status));
  if (talks.length > 1) {
    const open = talks.filter((status) => status !== "cancelled" && status !== "rejected");
    if (open.length > 0) {
      if (request.status === "converted") return "converted";
      if (open.some((status) => status === "countered" || status === "accepted")) return "in_negotiation";
      return request.status === "draft" ? "draft" : "sent";
    }
  }
  return request.status;
}

function cappedQuantity(requested: number, maximum: string | null | undefined) {
  if (maximum == null || maximum === "") return requested;
  const stock = Number(maximum);
  return Number.isFinite(stock) ? Math.min(requested, stock) : requested;
}

function choiceFor(request: PurchaseRequest, row: RequestSupplier) {
  if (row.soldOut || !row.askingPrice || !row.availability) return { action: "sold_out" as const, unit: "" };
  const several = request.suppliers.length > 1;
  const asks = request.suppliers.map((item) => Number(item.askingPrice?.amount)).filter((value) => value > 0);
  const baseline = several && asks.length ? (asks.reduce((sum, value) => sum + value, 0) / asks.length).toFixed(4) : row.askingPrice.amount;
  const buyer = request.offeredPrice ?? baseline;
  return tradeDecision({
    askingPrice: row.askingPrice,
    availability: row.availability,
    minimumQuantity: row.minimumQuantity ?? "0",
    maximumQuantity: row.maximumQuantity,
    soldOut: row.soldOut,
  }, cappedQuantity(Number(request.quantity), row.maximumQuantity), buyer, baseline, several);
}

function freightText(request: PurchaseRequest) {
  const row = request.suppliers[0];
  if (!row) return "Choose a supplier";
  if (row.freightStatus === "estimated" && row.freight) return formatMoney(row.freight);
  return "Freight on request";
}

function RequestModal({ productCode, quantity, pin, price, supplierId, onClose, onCreated }: {
  productCode: string;
  quantity: string;
  pin: string;
  price: string;
  supplierId?: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const products = useApiQuery("rfq-products", (signal) => listProducts({}, signal));
  const [code, setCode] = useState(productCode);
  const [amount, setAmount] = useState(quantity || "1000");
  const [destination, setDestination] = useState(pin || readDeliveryPin());
  const [buyerPrice, setBuyerPrice] = useState(price);
  const [priceDirty, setPriceDirty] = useState(Boolean(price));
  const [message, setMessage] = useState("");
  const [requiredBy, setRequiredBy] = useState("");
  const [paymentTerms, setPaymentTerms] = useState("");
  const [freightBasis, setFreightBasis] = useState<"standard" | "distance">("standard");
  const [busySupplier, setBusySupplier] = useState<string | null>(null);
  const [done, setDone] = useState<Record<string, string>>({});
  const [draftId, setDraftId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selected = (products.data ?? []).find((item) => item.productCode === code) ?? null;
  const pinOk = /^[1-9][0-9]{5}$/.test(destination);
  const quantityOk = Number(amount) > 0;
  const matches = useApiQuery(
    code && selected && pinOk && quantityOk ? `rfq-matches:${code}:${amount}:${destination}` : null,
    (signal) => listSupplierMatches(code, { quantity: amount, uom: selected?.uom.code ?? "KG", destinationPin: destination }, signal),
  );
  const listed = (matches.data?.matches ?? []).filter((match) => !supplierId || match.supplierUserId === supplierId);
  const several = listed.length > 1;
  const baseline = listed.length === 0 ? "" : several
    ? (listed.reduce((sum, match) => sum + Number(match.askingPrice.amount), 0) / listed.length).toFixed(4)
    : listed[0].askingPrice.amount;
  useEffect(() => {
    if (priceDirty || !baseline) return;
    setBuyerPrice(baseline);
  }, [baseline, priceDirty]);
  const ensureDraft = async () => {
    if (draftId) return draftId;
    if (!selected || !(Number(buyerPrice) > 0)) return null;
    const created = await createPurchaseRequest({
      productCode: selected.productCode,
      quantity: amount,
      uom: selected.uom.code,
      destinationPin: destination,
      freightBasis,
      requiredBy: requiredBy || undefined,
      paymentTerms: paymentTerms || undefined,
      message: message.trim() || undefined,
      offeredPrice: buyerPrice,
      supplierUserIds: listed.map((match) => match.supplierUserId),
    });
    setDraftId(created.id);
    onCreated();
    return created.id;
  };
  const askOrNegotiate = async (supplierUserId: string, offeredPrice: string) => {
    if (!selected || !(Number(offeredPrice) > 0)) return;
    setBusySupplier(supplierUserId);
    setError(null);
    setNotice(null);
    try {
      if (several) {
        const id = await ensureDraft();
        if (!id) return;
        await sendRequestSupplier(id, supplierUserId, offeredPrice);
        setDone((current) => ({ ...current, [supplierUserId]: "Asked — waiting for a reply" }));
        setNotice("Saved. The other suppliers stay on this request until you choose them after the reply.");
      } else {
        const draft = await createPurchaseRequest({
          productCode: selected.productCode,
          quantity: amount,
          uom: selected.uom.code,
          destinationPin: destination,
          freightBasis,
          requiredBy: requiredBy || undefined,
          paymentTerms: paymentTerms || undefined,
          message: message.trim() || undefined,
          offeredPrice,
          supplierUserIds: [supplierUserId],
        });
        await sendPurchaseRequest(draft.id);
        setDone((current) => ({ ...current, [supplierUserId]: "Negotiation sent" }));
        setNotice("Negotiation sent.");
      }
      onCreated();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusySupplier(null);
    }
  };
  const place = async (supplierUserId: string) => {
    if (!selected) return;
    setBusySupplier(supplierUserId);
    setError(null);
    setNotice(null);
    try {
      if (several) {
        const id = await ensureDraft();
        if (!id) return;
        await placeRequestSupplier(id, supplierUserId);
        setDone((current) => ({ ...current, [supplierUserId]: "Order placed" }));
        setNotice("Order placed. The other suppliers stay on this request.");
        matches.reload();
      } else {
        const result = await placeAtAsking({
          productCode: selected.productCode,
          supplierUserId,
          quantity: amount,
          destinationPin: destination,
          freightBasis,
          paymentTerms: paymentTerms || undefined,
        });
        if (!isPlacedOrder(result)) {
          setNotice("The order was not placed.");
          return;
        }
        setDone((current) => ({ ...current, [supplierUserId]: `Order ${result.orderNumber} placed` }));
        setNotice("Order placed.");
        matches.reload();
      }
      onCreated();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusySupplier(null);
    }
  };
  const saveDraft = async () => {
    setError(null);
    setNotice(null);
    try {
      const id = await ensureDraft();
      if (id) setNotice("Saved. Ask the supplier who is on request, then come back to this request and choose the others after they reply.");
    } catch (cause) {
      setError(getErrorMessage(cause));
    }
  };
  return (
    <Modal open className="modal--wide" title="Create purchase request" onClose={onClose}>
      <div className="form-grid request-form">
        <label>Product
          <select className="field-select" aria-label="Product" value={code} disabled={Boolean(draftId)} onChange={(event) => { setCode(event.target.value); setPriceDirty(false); }}>
            <option value="">Select a product</option>
            {(products.data ?? []).map((item) => <option key={item.productCode} value={item.productCode}>{item.name}</option>)}
          </select>
        </label>
        <label>Quantity<div className="input-combo"><Input value={amount} disabled={Boolean(draftId)} onChange={(event) => setAmount(event.target.value)} /><span>{selected?.uom.code ?? "UOM"}</span></div></label>
        <label>Delivery PIN<Input value={destination} disabled={Boolean(draftId)} onChange={(event) => setDestination(event.target.value)} placeholder="6-digit PIN" /></label>
        <label>{several ? "Average price" : "Your price"}
          <Input inputMode="decimal" aria-label={several ? "Average price" : "Your price"} value={buyerPrice} disabled={Boolean(draftId)} onChange={(event) => { setPriceDirty(true); setBuyerPrice(event.target.value); }} />
        </label>
        <label>Required by<Input type="date" aria-label="Required by" value={requiredBy} disabled={Boolean(draftId)} onChange={(event) => setRequiredBy(event.target.value)} /></label>
        <label>Payment terms
          <select className="field-select" aria-label="Payment terms" value={paymentTerms} disabled={Boolean(draftId)} onChange={(event) => setPaymentTerms(event.target.value)}>
            {PAYMENT_TERMS.map((term) => <option key={term.label} value={term.value}>{term.label}</option>)}
          </select>
        </label>
        <label>Freight basis
          <select className="field-select" aria-label="Freight basis" value={freightBasis} disabled={Boolean(draftId)} onChange={(event) => setFreightBasis(event.target.value as "standard" | "distance")}>
            <option value="standard">Normal freight</option>
            <option value="distance">Road distance</option>
          </select>
        </label>
        <label>Message<Input value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Optional note" /></label>
      </div>
      <p className="request-note">{several ? "Leave the average to order at each supplier’s asking price where stock allows. Change it and a supplier above that price is a negotiation. Asking one supplier saves the others on this request so you can choose them after the reply." : "Leave the asking price to place the order where stock allows. Change it to negotiate."} Advance lowers the material by 1%. Paying up to 14 days late adds 0.25% to 1.5%. Payable is an estimate.</p>
      {!code ? <p className="request-note">Choose a product first.</p> : !pinOk ? <p className="request-note">Enter a delivery PIN to see freight and the amount payable.</p> : matches.isLoading ? <p className="request-note">Matching suppliers…</p> : listed.length === 0 ? <p className="request-note">No supplier is listing this product.</p> : (
        <div className="market-table-wrap">
          <table className="market-table">
            <thead><tr><th>Supplier</th><th>Asking</th><th>Material</th><th>Freight</th><th>GST</th><th>Payable</th><th/></tr></thead>
            <tbody>
              {listed.map((match) => {
                const quantityForSupplier = cappedQuantity(Number(amount), match.maximumQuantity);
                const choice = tradeDecision(match, quantityForSupplier, buyerPrice, baseline, several);
                const unit = adjustUnitPrice(choice.unit || match.askingPrice.amount, paymentTerms);
                const material = previewOrderTotal(String(quantityForSupplier || amount), { amount: unit, currency: match.askingPrice.currency });
                const freight = match.comparison.freight;
                const charges = orderCharges(material, freight);
                const name = match.organisation.replace(/\s*\(demo supplier\)\s*$/i, "");
                const busy = busySupplier === match.supplierUserId;
                const finished = done[match.supplierUserId];
                return (
                  <tr key={match.supplierUserId}>
                    <td><strong>{name}</strong><small>{match.soldOut ? "Sold out" : titleCase(match.availability)}{match.maximumQuantity ? ` · ${Number(match.maximumQuantity).toLocaleString("en-IN")} ${match.uom.toLowerCase()}` : ""}{match.maximumQuantity && quantityForSupplier < Number(amount) ? ` · now ${quantityForSupplier.toLocaleString("en-IN")}` : ""}</small></td>
                    <td>{formatMoney(match.askingPrice)}</td>
                    <td>{formatMoney(material, 2)}</td>
                    <td>{freight ? formatMoney(freight) : "On request"}</td>
                    <td>{formatMoney(charges.gst, 2)}</td>
                    <td>{formatMoney(charges.payable, 2)}</td>
                    <td>
                      {finished ? <small>{finished}</small> : (
                        <>
                          {choice.action === "sold_out" && <Button disabled>Sold out</Button>}
                          {choice.action === "place" && <Button disabled={busy} onClick={() => void place(match.supplierUserId)}>Place order</Button>}
                          {choice.action === "negotiate" && <Button variant="secondary" disabled={busy || !(Number(choice.unit) > 0)} onClick={() => void askOrNegotiate(match.supplierUserId, choice.unit)}>Negotiate</Button>}
                          {choice.action === "ask" && <Button disabled={busy || !(Number(choice.unit) > 0)} onClick={() => void askOrNegotiate(match.supplierUserId, choice.unit)}>Ask {name}</Button>}
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {notice && <p className="request-note">{notice}</p>}
      {error && <p className="negative">{error}</p>}
      <div className="modal-actions">
        {several && !draftId && <Button variant="secondary" disabled={!selected || !pinOk || !quantityOk || !(Number(buyerPrice) > 0)} onClick={() => void saveDraft()}>Save draft</Button>}
        <Button variant="secondary" onClick={onClose}>Close</Button>
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
  const chooseSaved = async (id: string, supplierUserId: string, action: "send" | "order", offeredPrice?: string) => {
    setBusyId(`${id}:${supplierUserId}`);
    setError(null);
    try {
      if (action === "order") await placeRequestSupplier(id, supplierUserId);
      else await sendRequestSupplier(id, supplierUserId, offeredPrice);
      reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusyId(null);
    }
  };
  const act = async (id: string, action: "send" | "cancel" | "cancel-supplier", supplierUserId?: string) => {
    setBusyId(supplierUserId ? `${id}:${supplierUserId}` : id);
    setError(null);
    try {
      if (action === "send") await sendPurchaseRequest(id);
      else if (action === "cancel-supplier" && supplierUserId) await cancelRequestSupplier(id, supplierUserId);
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
                  <td><Badge tone={STATUS_TONE[headlineStatus(request)]}>{titleCase(headlineStatus(request))}</Badge></td>
                  <td onClick={(event) => event.stopPropagation()}>
                    {request.canSend && !several && <Button disabled={busyId === request.id} onClick={() => void act(request.id, "send")}>Send</Button>}
                    {!several && supplier?.negotiationId && <Button variant="secondary" onClick={() => navigate(`${paths.negotiations}?id=${encodeURIComponent(supplier.negotiationId ?? "")}`)}>Open negotiation</Button>}
                    {several && <small>{open ? "Each supplier is listed below" : "Expand for each supplier"}</small>}
                    {request.canCancel && !several && <Button variant="ghost" disabled={busyId === request.id} onClick={() => void act(request.id, "cancel")}>Cancel</Button>}
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
                            <td><strong><OrgLink organisationId={row.organisationId}>{row.organisation}</OrgLink></strong><small>{row.supplierName}</small>{row.supplyNote ? <small>{row.supplyNote}</small> : null}</td>
                            <td>{row.askingPrice ? formatMoney(row.askingPrice) : "—"}</td>
                            <td>{row.latestOffer ? formatMoney(row.latestOffer) : "—"}{row.quote.versusAverage && <small>{formatSignedMoney(row.quote.versusAverage)} vs market avg</small>}</td>
                            <td>{row.materialValue ? formatMoney(row.materialValue, 2) : "—"}</td>
                            <td>{row.freightStatus === "estimated" && row.freight ? formatMoney(row.freight) : "On request"}</td>
                            <td>{row.charges ? formatMoney(row.charges.gst, 2) : "—"}</td>
                            <td>{row.charges ? formatMoney(row.charges.payable, 2) : "—"}</td>
                            <td>{row.soldOut ? "Sold out" : row.negotiationStatus ? titleCase(row.negotiationStatus) : "Not sent"}</td>
                            <td>
                              {!row.negotiationId && buyer && !row.soldOut && (() => {
                                const choice = choiceFor(request, row);
                                const name = row.organisation.replace(/\s*\(demo supplier\)\s*$/i, "");
                                return (
                                  <>
                                    {choice.action === "place" && <Button disabled={busyId === `${request.id}:${row.supplierUserId}`} onClick={() => void chooseSaved(request.id, row.supplierUserId, "order")}>Place order</Button>}
                                    {choice.action === "negotiate" && <Button variant="secondary" disabled={busyId === `${request.id}:${row.supplierUserId}`} onClick={() => void chooseSaved(request.id, row.supplierUserId, "send", choice.unit)}>Negotiate</Button>}
                                    {choice.action === "ask" && <Button disabled={busyId === `${request.id}:${row.supplierUserId}`} onClick={() => void chooseSaved(request.id, row.supplierUserId, "send", choice.unit)}>Ask {name}</Button>}
                                  </>
                                );
                              })()}
                              {row.soldOut && <small>Sold out</small>}
                              {row.negotiationId && <Button variant="secondary" onClick={() => navigate(`${paths.negotiations}?id=${encodeURIComponent(row.negotiationId ?? "")}`)}>Open negotiation</Button>}
                              {buyer && row.negotiationStatus === "accepted" && row.negotiationId && !row.soldOut && <Button onClick={() => void placeOrder(row.negotiationId ?? "")}>Place order</Button>}
                              {buyer && row.negotiationId && row.negotiationStatus && !["accepted", "rejected", "cancelled"].includes(row.negotiationStatus) && (
                                <Button variant="ghost" disabled={busyId === `${request.id}:${row.supplierUserId}`} onClick={() => void act(request.id, "cancel-supplier", row.supplierUserId)}>Cancel</Button>
                              )}
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
          price={searchParams.get("price") ?? ""}
          supplierId={searchParams.get("supplier") ?? undefined}
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
