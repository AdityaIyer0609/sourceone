import { BarChart3, Check, Clock3, History, MessageSquareText, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { canAccess } from "../app/navigation";
import { paths } from "../app/paths";
import { readSession } from "../lib/api/auth";
import { AsyncContent } from "../components/feedback/AsyncContent";
import { CreateOrderModal } from "../components/negotiation/CreateOrderModal";
import { OfferModal } from "../components/negotiation/OfferModal";
import { RequirementList } from "../components/product/RequirementList";
import { OrgLink } from "../components/supplier/OrgLink";
import { Badge, Button, Heading } from "../components/ui";
import { ApiError, getErrorMessage } from "../lib/api/client";
import { acceptNegotiation,
  cancelNegotiation,
  listNegotiations,
  rejectNegotiation,
  submitOffer,
  type Negotiation,
  type NegotiationStatus,
} from "../lib/api/negotiations";
import { listOrders, type Order } from "../lib/api/orders";
import { useApiQuery } from "../lib/api/useApiQuery";
import { formatDate, formatDateTime, formatMoney, formatSignedMoney, titleCase } from "../lib/pricingFormat";

const STATUS_TONES: Record<NegotiationStatus, "neutral" | "positive" | "warning" | "negative" | "info"> = {
  draft: "info",
  open: "info",
  countered: "warning",
  accepted: "positive",
  rejected: "negative",
  cancelled: "neutral",
};

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((word) => word[0].toUpperCase()).join("");
}

function quantityText(quantity: string, uom: string) {
  return `${Number(quantity).toLocaleString("en-IN")} ${uom.toLowerCase()}`;
}

function needsReply(status: NegotiationStatus) {
  return status === "draft" || status === "open" || status === "countered";
}

function listSummary(item: Negotiation) {
  const latest = item.versions.at(-1);
  const price = latest ? `${formatMoney(latest.offeredPrice)} / ${item.uom.toLowerCase()}` : "No offer yet";
  if (!needsReply(item.status) || !item.awaiting) return price;
  if (item.awaiting === item.viewerRole) return `${price} · Your turn`;
  const waiting = item.awaiting === "buyer" ? item.buyer.organisation : item.supplier.organisation;
  return `${price} · Waiting for ${waiting}`;
}

function NegotiationRoom({ negotiation, order, onChanged, onOrdersChanged }: { negotiation: Negotiation; order: Order | null; onChanged: () => void; onOrdersChanged: () => void }) {
  const navigate = useNavigate();
  const latest = negotiation.versions.at(-1) ?? null;
  const [version, setVersion] = useState(latest?.versionNumber ?? 0);
  const [counterOpen, setCounterOpen] = useState(false);
  const [orderOpen, setOrderOpen] = useState(false);
  const viewOrder = (target: Order) => navigate(`${paths.orders}?id=${encodeURIComponent(target.id)}`);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const shown = negotiation.versions.find((item) => item.versionNumber === version) ?? latest;
  const { allowedActions: can, benchmark, negotiated } = negotiation;
  const myTurn = can.offer;
  const otherParty = negotiation.viewerRole === "buyer" ? negotiation.supplier.organisation : negotiation.buyer.organisation;
  const unit = negotiation.uom.toLowerCase();
  const partyName = (role: "buyer" | "supplier") => negotiation[role].organisation;
  const offerLabel = (role: "buyer" | "supplier") => (role === negotiation.viewerRole ? "Your offer" : `${titleCase(role)} offer`);
  const benchmarkText = benchmark.value ? `${formatMoney(benchmark.value)} / ${unit}` : "Rate on request";

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };

  const statusLine = negotiation.status === "accepted" || negotiation.status === "rejected" || negotiation.status === "cancelled"
    ? `${titleCase(negotiation.status)}${negotiation.closedAt ? ` · ${formatDateTime(negotiation.closedAt)}` : ""}`
    : negotiation.awaiting ? `${titleCase(negotiation.status)} · Awaiting ${negotiation.awaiting === negotiation.viewerRole ? "you" : negotiation.awaiting}` : titleCase(negotiation.status);

  return (
    <>
      <div className="page-heading"><div><small>NEGOTIATION ROOM · {negotiation.negotiationNumber}</small><Heading level={1}>{negotiation.product.name} · {quantityText(negotiation.quantity, negotiation.uom)}</Heading><p>{negotiation.buyer.organisation} ↔ {negotiation.viewerRole === "buyer" ? <OrgLink organisationId={negotiation.supplier.organisationId}>{negotiation.supplier.organisation}</OrgLink> : negotiation.supplier.organisation}{negotiation.requiredBy ? ` · Required by ${negotiation.requiredBy}` : ""}{negotiation.paymentTerms ? ` · ${negotiation.paymentTerms}` : ""}</p></div><Badge tone={STATUS_TONES[negotiation.status]}><Clock3 size={14} /> {statusLine}</Badge></div>
      <div className="negotiation-layout">
        <section className="offer-main">
          {shown ? (
            <>
              <div className="offer-head"><div><div className="avatar avatar--square">{initials(partyName(shown.offeredBy))}</div><span><strong>{partyName(shown.offeredBy)}</strong><small>{shown.author} · {offerLabel(shown.offeredBy)}</small></span></div><Badge tone={negotiated?.versionNumber === shown.versionNumber ? "positive" : shown === latest ? "positive" : "neutral"}>{negotiated?.versionNumber === shown.versionNumber ? "ACCEPTED" : shown === latest ? "LATEST OFFER" : "EARLIER OFFER"} · V{shown.versionNumber}</Badge></div>
              <div className="offer-price"><small>{negotiated?.versionNumber === shown.versionNumber ? "NEGOTIATED PRICE" : "OFFERED RATE"}</small><strong>{formatMoney(shown.offeredPrice)}<em>/ {unit}</em></strong><span>Plenza benchmark at start: {benchmarkText}{benchmark.asOfDate ? ` (as of ${formatDate(benchmark.asOfDate)})` : ""}{negotiation.quote.versusAverage ? ` · ${formatSignedMoney(negotiation.quote.versusAverage)} vs market avg` : ""}</span></div>
              <div className="offer-terms">{[
                ["Quantity", quantityText(shown.quantity, shown.uom)],
                ["Currency", `${negotiation.currency} / ${unit}`],
                ["Plenza benchmark (reference)", benchmarkText],
                ["Negotiated price", negotiated ? `${formatMoney(negotiated.price)} / ${unit}` : "Not agreed yet"],
                ["Benchmark as of", benchmark.asOfDate ? `${formatDate(benchmark.asOfDate)}${benchmark.state === "stale" ? " · Stale" : ""}` : "—"],
                ["Offered", formatDateTime(shown.createdAt)],
              ].map(([label, value], index) => <div className={index === 3 ? "emphasis" : ""} key={label}><small>{label}</small><strong>{value}</strong></div>)}</div>
              <div className="offer-message"><MessageSquareText size={18} /><p>{shown.message ? `“${shown.message}”` : "No message with this offer."}</p></div>
              {negotiation.requirements.length > 0 && <RequirementList rows={negotiation.requirements} />}
            </>
          ) : (
            <div className="offer-message"><MessageSquareText size={18} /><p>This negotiation is a draft. Submit the first offer to send it to {negotiation.supplier.organisation}.</p></div>
          )}
          <div className="offer-actions">
            {myTurn && can.accept && <Button disabled={busy} onClick={() => run(() => acceptNegotiation(negotiation.id))}><Check size={17} /> Accept offer</Button>}
            {myTurn && <Button variant="dark" disabled={busy} onClick={() => setCounterOpen(true)}>{latest ? "Send counter offer" : "Submit offer"}</Button>}
            {myTurn && can.reject && <Button variant="secondary" disabled={busy} onClick={() => run(() => rejectNegotiation(negotiation.id))}>Reject offer</Button>}
            {!myTurn && negotiation.status !== "accepted" && negotiation.status !== "rejected" && negotiation.status !== "cancelled" && (
              <p className="offer-status">Waiting for {otherParty} to respond. Accept and counter stay hidden until it is your turn.</p>
            )}
            {negotiation.status === "accepted" && !order && negotiation.viewerRole === "supplier" && (
              <p className="offer-status">Offer accepted. {negotiation.buyer.organisation} can place the order.</p>
            )}
            {negotiation.status === "rejected" && <p className="offer-status">This negotiation was rejected.{negotiation.closedReason ? ` ${negotiation.closedReason}` : ""}</p>}
            {negotiation.status === "cancelled" && <p className="offer-status">This negotiation was cancelled.{negotiation.closedReason ? ` ${negotiation.closedReason}` : ""}</p>}
            {can.cancel && <Button variant="ghost" disabled={busy} onClick={() => run(() => cancelNegotiation(negotiation.id))}>Cancel negotiation</Button>}
            {order ? (
              <Button variant="ghost" onClick={() => viewOrder(order)}>Order {order.orderNumber} · {titleCase(order.status)}</Button>
            ) : negotiation.status === "accepted" && negotiation.viewerRole === "buyer" && (
              <Button onClick={() => setOrderOpen(true)}>Create order</Button>
            )}
          </div>
          {error ? <p className="negative" role="alert">{getErrorMessage(error)}{error instanceof ApiError && error.code ? ` (${error.code})` : ""}</p> : null}
          <p className="approval-note"><ShieldCheck size={15} /> {negotiation.status === "accepted" ? "The negotiated price is fixed at the accepted offer. No further offers." : negotiation.status === "rejected" || negotiation.status === "cancelled" ? (negotiation.closedReason ? `Reason: ${negotiation.closedReason}` : `This negotiation is ${negotiation.status}.`) : myTurn ? "Accepting fixes the negotiated price at the accepted offer version. No order is created." : `Waiting for ${otherParty}.`}</p>
        </section>
        <aside className="version-panel">
          <div className="section-title"><div><small>AUDIT TRAIL</small><Heading level={2}>Offer versions</Heading></div><History size={18} /></div>
          <div className="version-list">{[...negotiation.versions].reverse().map((offer) => <Button variant="ghost" className={`version-item ${shown?.versionNumber === offer.versionNumber ? "is-active" : ""}`} key={offer.versionNumber} onClick={() => setVersion(offer.versionNumber)}><span className="version-node">V{offer.versionNumber}</span><span><strong>{offerLabel(offer.offeredBy)}{offer === latest ? " · Current" : ""}</strong><small>{formatDateTime(offer.createdAt)}</small><b>{formatMoney(offer.offeredPrice)}/{unit}</b><small>{quantityText(offer.quantity, offer.uom)} · {offer.author}</small></span></Button>)}</div>
          {negotiated ? (
            <div className="saving-callout"><span>Negotiated price</span><strong>{formatMoney(negotiated.price)}/{unit}</strong><small>Accepted offer V{negotiated.versionNumber} · {quantityText(negotiated.quantity, negotiated.uom)}</small></div>
          ) : (
            <div className="saving-callout"><span>Plenza benchmark at start</span><strong>{benchmarkText}</strong><small>Reference value only · not an offer</small></div>
          )}
        </aside>
      </div>
      <section className="benchmark-bar"><BarChart3 size={22}/><div><strong>Plenza benchmark (reference)</strong><small>{benchmark.basis === "ASKING_AVERAGE/GST_EXCLUDED" ? "Average of supplier asking prices when this negotiation started. " : ""}{benchmark.seriesCode ? `${benchmark.seriesCode} · ${benchmark.basis ?? ""} · ` : ""}Snapshot taken when the negotiation started</small></div><span><small>BENCHMARK</small><strong>{benchmarkText}</strong></span><div className="benchmark-scale"><i/><b>{latest ? offerLabel(latest.offeredBy) : "No offer yet"}</b></div><span><small>LATEST OFFER</small><strong>{latest ? `${formatMoney(latest.offeredPrice)} / ${unit}` : "—"}</strong></span>{negotiation.destinationPin && <span><small>ESTIMATED FREIGHT</small><strong>{negotiation.freightStatus === "estimated" && negotiation.freight ? formatMoney(negotiation.freight) : "On request"}</strong><small>PIN {negotiation.destinationPin}</small></span>}</section>
      {orderOpen && <CreateOrderModal negotiation={negotiation} onClose={() => setOrderOpen(false)} onCreated={onOrdersChanged} onViewOrder={viewOrder} />}
      {counterOpen && (
        <OfferModal
          title={latest ? "Send counter offer" : "Submit offer"}
          productName={negotiation.product.name}
          context={`${negotiation.negotiationNumber} · Plenza benchmark (reference): ${benchmarkText}`}
          currency={negotiation.currency}
          uom={negotiation.uom}
          initialQuantity={latest?.quantity ?? negotiation.quantity}
          submitLabel={latest ? "Send counter offer" : "Submit offer"}
          onClose={() => setCounterOpen(false)}
          onSubmit={async (input) => {
            await submitOffer(negotiation.id, input);
            setCounterOpen(false);
            onChanged();
          }}
        />
      )}
    </>
  );
}

export function NegotiationsPage() {
  const allowed = canAccess(readSession()?.user.roles ?? [], ["buyer", "supplier"]);
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: negotiations = [], error, isLoading, reload } = useApiQuery(allowed ? "negotiations" : null, (signal) => listNegotiations(signal));
  const selected = negotiations.find((item) => item.id === searchParams.get("id")) ?? negotiations[0] ?? null;
  const orders = useApiQuery(allowed ? "orders" : null, (signal) => listOrders(signal));
  if (!allowed) return <Navigate to={paths.marketplace} replace />;
  const order = orders.data?.find((item) => item.negotiation.id === selected?.id) ?? null;
  const listed = [...negotiations].sort((left, right) => Number(needsReply(right.status)) - Number(needsReply(left.status)) || right.updatedAt.localeCompare(left.updatedAt));
  return (
    <div className="page">
      <AsyncContent isLoading={isLoading && !negotiations.length} error={error} onRetry={reload} isEmpty={!negotiations.length} emptyTitle="No negotiations yet" emptyMessage="Open a product and choose “Request negotiated rate” to start one." loadingLabel="Loading negotiations…">
        <div className="negotiation-desk">
          <aside className="negotiation-list" aria-label="Negotiations">
            {listed.map((item) => (
              <Button key={item.id} variant="ghost" className={`negotiation-row${item.id === selected?.id ? " is-active" : ""}`} onClick={() => setSearchParams({ id: item.id })}>
                <span>
                  <strong>{item.product.name}</strong>
                  <small>{item.negotiationNumber}</small>
                  <small>{listSummary(item)}</small>
                </span>
                <Badge tone={STATUS_TONES[item.status]}>{titleCase(item.status)}</Badge>
              </Button>
            ))}
          </aside>
          <div>
            {selected && <NegotiationRoom key={`${selected.id}:${selected.versions.length}:${selected.status}`} negotiation={selected} order={order} onChanged={reload} onOrdersChanged={orders.reload} />}
          </div>
        </div>
      </AsyncContent>
    </div>
  );
}
