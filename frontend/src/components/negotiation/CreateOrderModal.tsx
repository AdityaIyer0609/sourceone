import { useState } from "react";
import { ApiError, getErrorMessage } from "../../lib/api/client";
import type { Negotiation } from "../../lib/api/negotiations";
import { createOrderFromNegotiation, type Order } from "../../lib/api/orders";
import { BENCHMARK_GLYPH, formatMoney, previewOrderTotal, titleCase } from "../../lib/pricingFormat";
import { ProductVisual } from "../product/ProductVisual";
import { Button, Modal } from "../ui";

/** Confirms placing an order at the accepted negotiated price, then shows the created order. */
export function CreateOrderModal({ negotiation, onClose, onCreated, onViewOrder }: {
  negotiation: Negotiation;
  onClose: () => void;
  onCreated: (order: Order) => void;
  onViewOrder: (order: Order) => void;
}) {
  const [order, setOrder] = useState<Order | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const negotiated = negotiation.negotiated;
  if (!negotiated) return null;
  const unit = negotiated.uom.toLowerCase();
  const quantity = `${Number(negotiated.quantity).toLocaleString("en-IN")} ${unit}`;

  const place = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await createOrderFromNegotiation(negotiation.id);
      setOrder(created);
      onCreated(created);
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
        <span><small>Total value</small><strong>{formatMoney(order?.totalValue ?? previewOrderTotal(negotiated.quantity, negotiated.price), 2)}</strong></span>
      </div>
      <p><small>{order ? "The order keeps this negotiated price; later benchmark changes do not affect it." : "Total = quantity × negotiated unit price. Freight and GST are not included."}</small></p>
      {error ? <p className="negative" role="alert">{getErrorMessage(error)}{error instanceof ApiError && error.code ? ` (${error.code})` : ""}</p> : null}
      <div className="modal-actions">
        <Button variant="secondary" onClick={onClose}>Close</Button>
        {order ? <Button onClick={() => onViewOrder(order)}>View order</Button> : <Button disabled={busy} onClick={place}>Place order</Button>}
      </div>
    </Modal>
  );
}
