import { useState, type ReactNode } from "react";
import { ApiError, getErrorMessage } from "../../lib/api/client";
import type { OfferInput } from "../../lib/api/negotiations";
import { BENCHMARK_GLYPH } from "../../lib/pricingFormat";
import { ProductVisual } from "../product/ProductVisual";
import { Button, Input, Modal } from "../ui";

/** Quantity + offered price + message form, shared by "start negotiation" and "counter offer". */
export function OfferModal({
  title,
  productName,
  context,
  currency,
  uom,
  initialQuantity,
  submitLabel,
  onClose,
  onSubmit,
}: {
  title: string;
  productName: string;
  context: ReactNode;
  currency: string;
  uom: string;
  initialQuantity: string;
  submitLabel: string;
  onClose: () => void;
  onSubmit: (input: OfferInput & { quantity: string }) => Promise<void>;
}) {
  const [quantity, setQuantity] = useState(initialQuantity);
  const [price, setPrice] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const valid = Number(quantity) > 0 && Number(price) > 0;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ quantity, offeredPrice: price, message: message.trim() || undefined });
    } catch (caught) {
      setError(caught);
      setBusy(false);
    }
  };

  return (
    <Modal open title={title} onClose={onClose}>
      <div className="modal-product"><ProductVisual glyph={BENCHMARK_GLYPH} /><div><strong>{productName}</strong><small>{context}</small></div></div>
      <div className="modal-cost">
        <span><small>Quantity ({uom})</small><strong><Input inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} aria-label="Quantity" /></strong></span>
        <span><small>Offered price ({currency} / {uom.toLowerCase()})</small><strong><Input inputMode="decimal" value={price} placeholder="0.00" onChange={(event) => setPrice(event.target.value)} aria-label="Offered price" /></strong></span>
      </div>
      <Input value={message} placeholder="Message to the other party (optional)" onChange={(event) => setMessage(event.target.value)} aria-label="Message" />
      {error ? <p className="negative" role="alert">{getErrorMessage(error)}{error instanceof ApiError && error.code ? ` (${error.code})` : ""}</p> : null}
      <div className="modal-actions">
        <Button variant="secondary" onClick={onClose}>Close</Button>
        <Button disabled={!valid || busy} onClick={submit}>{submitLabel}</Button>
      </div>
    </Modal>
  );
}
