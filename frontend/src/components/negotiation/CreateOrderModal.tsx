import { useEffect, useState } from "react";
import { ApiError, getErrorMessage } from "../../lib/api/client";
import { readDeliveryPin } from "../../lib/deliveryPin";
import { estimateFreight, shownFreight, type FreightBasis, type FreightEstimate } from "../../lib/api/freight";
import type { Negotiation } from "../../lib/api/negotiations";
import { createOrderFromNegotiation, isPlacedOrder, type Order } from "../../lib/api/orders";
import { BENCHMARK_GLYPH, formatMoney, GST_RATE_PERCENT, orderCharges, previewOrderTotal, titleCase } from "../../lib/pricingFormat";
import { ProductVisual } from "../product/ProductVisual";
import { Button, Input, Modal } from "../ui";

/** Confirms placing an order at the accepted negotiated price, then shows the created order. */
export function CreateOrderModal({ negotiation, onClose, onCreated, onViewOrder }: {
  negotiation: Negotiation;
  onClose: () => void;
  onCreated: (order: Order) => void;
  onViewOrder: (order: Order) => void;
}) {
  const [order, setOrder] = useState<Order | null>(null);
  const [pin, setPin] = useState(negotiation.destinationPin || readDeliveryPin());
  const [basis, setBasis] = useState<FreightBasis>(negotiation.freightBasis ?? "standard");
  const [estimate, setEstimate] = useState<FreightEstimate | null>(null);
  const [estimating, setEstimating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const negotiated = negotiation.negotiated;
  const pinOk = /^[1-9][0-9]{5}$/.test(pin);
  useEffect(() => {
    if (!negotiated || !pinOk) {
      setEstimate(null);
      return;
    }
    let cancelled = false;
    setEstimating(true);
    estimateFreight({
      supplierUserId: negotiation.supplierUserId,
      productCode: negotiation.product.productCode,
      quantity: negotiated.quantity,
      destinationPin: pin,
    }).then((result) => {
      if (!cancelled) setEstimate(result);
    }).catch((caught) => {
      if (!cancelled) {
        setEstimate(null);
        setError(caught);
      }
    }).finally(() => {
      if (!cancelled) setEstimating(false);
    });
    return () => { cancelled = true; };
  }, [negotiated, negotiation.supplierUserId, negotiation.product.productCode, pin, pinOk]);
  if (!negotiated) return null;
  const unit = negotiated.uom.toLowerCase();
  const quantity = `${Number(negotiated.quantity).toLocaleString("en-IN")} ${unit}`;
  const shown = estimate ? shownFreight(estimate, basis) : null;
  const material = order?.totalValue ?? previewOrderTotal(negotiated.quantity, negotiated.price);
  const freightMoney = order
    ? (order.freightStatus === "estimated" ? order.freight : null)
    : (shown?.status === "estimated" ? shown.freight : null);
  const charges = orderCharges(material, freightMoney);
  const freightText = !pinOk ? "Enter a delivery PIN" : estimating ? "Calculating…" : shown?.status === "estimated" && shown.freight ? formatMoney(shown.freight) : "Freight on request";

  const place = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await createOrderFromNegotiation(negotiation.id, { destinationPin: pin, freightBasis: basis });
      if (isPlacedOrder(created)) {
        setOrder(created);
        onCreated(created);
      } else {
        setError(new Error("The order was not placed."));
      }
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title={order ? "Order placed" : "Create order"} onClose={onClose}>
      <div className="modal-product"><ProductVisual glyph={BENCHMARK_GLYPH} /><div><strong>{negotiation.product.name}</strong><small>{negotiation.negotiationNumber} · accepted offer V{negotiated.versionNumber} · {negotiation.supplier.organisation}</small></div></div>
      <div className="modal-cost">
        {order && <span><small>Order number</small><strong>{order.orderNumber} · {titleCase(order.status)}</strong></span>}
        <span><small>Quantity</small><strong>{order ? `${Number(order.quantity).toLocaleString("en-IN")} ${unit}` : quantity}</strong></span>
        <span><small>Negotiated unit price</small><strong>{formatMoney(order?.agreedPrice.unitPrice ?? negotiated.price, 4)} / {unit}</strong></span>
        <span><small>Material (negotiated)</small><strong>{formatMoney(material, 2)}</strong></span>
      </div>
      <div className="order-delivery">
        {order ? (
          <div className="order-freight"><small>Delivery PIN</small><strong>{order.destinationPin ?? "—"}</strong></div>
        ) : (
          <label>Delivery PIN<Input value={pin} inputMode="numeric" aria-label="Delivery PIN" placeholder="6-digit PIN" onChange={(event) => setPin(event.target.value)} /></label>
        )}
        {!order && (
          <div className="freight-basis" role="group" aria-label="Freight basis">
            <Button variant="ghost" className={`filter-chip${basis === "standard" ? " is-active" : ""}`} onClick={() => setBasis("standard")}>Normal freight</Button>
            <Button variant="ghost" className={`filter-chip${basis === "distance" ? " is-active" : ""}`} onClick={() => setBasis("distance")}>Road distance</Button>
          </div>
        )}
        <div className="order-freight">
          <small>Estimated freight{shown?.label ? ` · ${shown.label}` : ""}</small>
          <strong>{order ? (order.freightStatus === "estimated" && order.freight ? formatMoney(order.freight) : "Freight on request") : freightText}</strong>
        </div>
        <div className="order-freight">
          <small>GST {GST_RATE_PERCENT}%{freightMoney ? " on material and freight" : " on material"}</small>
          <strong>{formatMoney(charges.gst)}</strong>
        </div>
        <div className="order-freight order-payable">
          <small>Amount payable</small>
          <strong>{formatMoney(charges.payable)}</strong>
        </div>
      </div>
      <p className="order-note">{`Amount payable adds the estimated freight, when it is known, and ${GST_RATE_PERCENT}% GST. The negotiated price stays the material rate.`}</p>
      {error ? <p className="negative" role="alert">{getErrorMessage(error)}{error instanceof ApiError && error.code ? ` (${error.code})` : ""}</p> : null}
      <div className="modal-actions">
        <Button variant="secondary" onClick={onClose}>Close</Button>
        {order ? <Button onClick={() => onViewOrder(order)}>View order</Button> : <Button disabled={busy || !pinOk} onClick={place}>Place order</Button>}
      </div>
    </Modal>
  );
}
