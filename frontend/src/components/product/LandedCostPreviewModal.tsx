import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { getErrorMessage } from "../../lib/api/client";
import { estimateFreight, type FreightEstimate } from "../../lib/api/freight";
import { formatMoney } from "../../lib/pricingFormat";
import { Button, Modal } from "../ui";
import { ProductVisual } from "./ProductVisual";

export interface LandedSupplier {
  id: string
  organisation: string
  name: string
  askingPrice?: string
  originPin?: string | null
  originLabel?: string | null
}

export function LandedCostPreviewModal({
  open, productName, productCode, quantity, uom, destinationPin, suppliers, onClose, onOpenCalculator,
}: {
  open: boolean
  productName: string
  productCode: string
  quantity: number
  uom: string
  destinationPin: string
  suppliers: LandedSupplier[]
  onClose: () => void
  onOpenCalculator: () => void
}) {
  const [supplierId, setSupplierId] = useState(suppliers[0]?.id ?? "")
  const [estimate, setEstimate] = useState<FreightEstimate | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const supplier = suppliers.find((item) => item.id === supplierId) ?? suppliers[0]
  const pinOk = /^[1-9][0-9]{5}$/.test(destinationPin)

  const calculate = async () => {
    if (!supplier || !pinOk || quantity <= 0) return
    setBusy(true)
    setError(null)
    try {
      setEstimate(await estimateFreight({
        supplierUserId: supplier.id,
        productCode,
        quantity: String(quantity),
        destinationPin,
      }))
    } catch (cause) {
      setEstimate(null)
      setError(getErrorMessage(cause))
    } finally {
      setBusy(false)
    }
  }

  const money = (value: FreightEstimate["freight"]) => (value ? formatMoney(value) : "Freight on request")
  return (
    <Modal open={open} title="Landed cost preview" onClose={onClose}>
      <div className="modal-product">
        <ProductVisual glyph="COIL" />
        <div>
          <strong>{productName}</strong>
          <small>{quantity.toLocaleString("en-IN")} {uom.toLowerCase()} · {supplier ? `${supplier.originLabel ?? supplier.originPin ?? "Origin on request"} to ${destinationPin}` : "Choose a supplier"}</small>
        </div>
      </div>
      <label className="delivery-field">Supplier
        <select className="input" aria-label="Supplier" value={supplier?.id ?? ""} onChange={(event) => { setSupplierId(event.target.value); setEstimate(null) }} style={{ border: "1px solid var(--line)", height: 36, marginTop: 6, padding: "0 8px", width: "100%" }}>
          {suppliers.length === 0 ? <option value="">No supplier is listing this product</option> : suppliers.map((item) => (
            <option key={item.id} value={item.id}>{item.organisation} · {item.name}{item.askingPrice ? ` · ${item.askingPrice}` : ""}</option>
          ))}
        </select>
      </label>
      {error && <p className="negative">{error}</p>}
      <div className="modal-cost">
        <span><small>Supplier asking price</small><strong>{estimate ? formatMoney(estimate.supplierAskingPrice) : "—"} / {uom.toLowerCase()}</strong></span>
        <span><small>Material</small><strong>{estimate ? formatMoney(estimate.materialValue) : "—"}</strong></span>
        <span><small>Estimated freight</small><strong>{estimate ? (estimate.freightStatus === "estimated" ? money(estimate.freight) : "Freight on request") : "—"}</strong></span>
        <span><small>Estimated landed / {uom.toLowerCase()}</small><strong>{estimate?.landedCostPerUnit ? formatMoney(estimate.landedCostPerUnit) : estimate ? "Freight on request" : "—"}</strong></span>
        <span><small>Estimated landed value</small><strong>{estimate?.landedValue ? formatMoney(estimate.landedValue) : estimate ? "Freight on request" : "—"}</strong></span>
      </div>
      <p><small>{estimate?.note ?? "Estimate only. The SourceOne benchmark and the negotiated price stay separate."}</small></p>
      <div className="modal-actions">
        <Button variant="secondary" onClick={onClose}>Close</Button>
        <Button disabled={!supplier || !pinOk || busy} onClick={() => void calculate()}>{busy ? "Calculating…" : "Calculate"} <ArrowRight size={16}/></Button>
        <Button variant="ghost" onClick={onOpenCalculator}>Open full calculator</Button>
      </div>
    </Modal>
  )
}
