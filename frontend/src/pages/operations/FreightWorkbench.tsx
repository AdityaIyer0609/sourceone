import { ArrowRight, Truck } from "lucide-react";
import { useEffect, useState } from "react";
import { onDeliveryPinChange, readDeliveryPin } from "../../lib/deliveryPin";
import { Badge, Button, Input } from "../../components/ui";
import { getErrorMessage } from "../../lib/api/client";
import { estimateFreight, shownFreight, type FreightBasis, type FreightEstimate } from "../../lib/api/freight";
import { listProductListings, type SupplierListing } from "../../lib/api/listings";
import { listProducts } from "../../lib/api/products";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatMoney } from "../../lib/pricingFormat";

export function FreightWorkbench() {
  const products = useApiQuery("freight-products", (signal) => listProducts({}, signal));
  const [productCode, setProductCode] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [quantity, setQuantity] = useState("5000");
  const [destinationPin, setDestinationPin] = useState(readDeliveryPin);
  useEffect(() => onDeliveryPinChange(() => setDestinationPin(readDeliveryPin())), []);
  const [estimate, setEstimate] = useState<FreightEstimate | null>(null);
  const [basis, setBasis] = useState<FreightBasis>("standard");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const selectedCode = productCode || products.data?.[0]?.productCode || "";
  const listings = useApiQuery(selectedCode ? `freight-listings:${selectedCode}` : null, (signal) => listProductListings(selectedCode, undefined, signal));
  const offers = listings.data ?? [];
  const supplier = offers.find((item) => item.supplierUserId === supplierId) ?? offers[0];
  const product = products.data?.find((item) => item.productCode === selectedCode);

  const calculate = async () => {
    if (!supplier || !product) return;
    setBusy(true);
    setError(null);
    try {
      setEstimate(await estimateFreight({
        supplierUserId: supplier.supplierUserId,
        productCode: product.productCode,
        quantity,
        destinationPin,
      }));
    } catch (cause) {
      setEstimate(null);
      setError(getErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  const line = (value: FreightEstimate["freight"], fallback = "Freight on request") => (value ? formatMoney(value) : fallback);
  return (
    <div className="freight-layout">
      <section className="workbench">
        <div className="step-label"><span>01</span><div><strong>Material & quantity</strong><small>What are you moving?</small></div></div>
        <div className="form-grid">
          <label>Item
            <select className="input" aria-label="Item" value={selectedCode} onChange={(event) => { setProductCode(event.target.value); setSupplierId(""); setEstimate(null); }}>
              {(products.data ?? []).map((item) => <option key={item.productCode} value={item.productCode}>{item.name}</option>)}
            </select>
          </label>
          <label>Quantity<div className="input-combo"><Input value={quantity} onChange={(event) => setQuantity(event.target.value)} /><span>{product?.uom.code ?? "KG"}</span></div></label>
        </div>
        <div className="step-label"><span>02</span><div><strong>Route</strong><small>Supply point to delivery location</small></div></div>
        <label>Supplier
          <select className="input" aria-label="Supplier" value={supplier?.supplierUserId ?? ""} onChange={(event) => { setSupplierId(event.target.value); setEstimate(null); }}>
            {offers.length === 0 ? <option value="">No supplier is listing this product</option> : offers.map((item) => <option key={item.supplierUserId} value={item.supplierUserId}>{item.organisation} · {item.supplierName}</option>)}
          </select>
        </label>
        <div className="route-fields">
          <label>Dispatch PIN<Input readOnly value={supplier?.originPin ?? ""} placeholder="Origin on request" /></label>
          <div className="route-line"><span/><Truck size={18}/><span/></div>
          <label>Delivery PIN<Input value={destinationPin} onChange={(event) => setDestinationPin(event.target.value)} /></label>
        </div>
        <div className="step-label"><span>03</span><div><strong>Commercial terms</strong><small>Supplier asking price, kept separate from the Plenza benchmark</small></div></div>
        <div className="form-grid">
          <label>Supplier asking price<Input readOnly value={supplier ? `${formatMoney(supplier.askingPrice)} / kg` : "—"} /></label>
          <label>Estimate<Input readOnly value="Freight is an estimate only" /></label>
        </div>
        <div className="freight-basis" role="group" aria-label="Freight basis">
          <Button variant="ghost" className={`filter-chip${basis === "standard" ? " is-active" : ""}`} onClick={() => setBasis("standard")}>Normal freight</Button>
          <Button variant="ghost" className={`filter-chip${basis === "distance" ? " is-active" : ""}`} onClick={() => setBasis("distance")}>Road distance</Button>
        </div>
        {error && <p className="negative">{error}</p>}
        <Button className="wide-button" disabled={!supplier || busy} onClick={() => void calculate()}>{busy ? "Calculating…" : "Calculate best landed cost"} <ArrowRight size={17}/></Button>
      </section>
      <LandedSummary estimate={estimate} supplier={supplier} line={line} basis={basis} onBasis={setBasis} />
    </div>
  );
}

function LandedSummary({
  estimate, supplier, line, basis, onBasis,
}: {
  estimate: FreightEstimate | null
  supplier: SupplierListing | undefined
  line: (value: FreightEstimate["freight"], fallback?: string) => string
  basis: FreightBasis
  onBasis: (basis: FreightBasis) => void
}) {
  const shown = estimate ? shownFreight(estimate, basis) : null;
  const onRequest = shown != null && shown.status !== "estimated";
  const badge = !estimate
    ? "ESTIMATE"
    : onRequest
      ? "ON REQUEST"
      : basis === "distance"
        ? "ROAD DISTANCE"
        : estimate.match === "lane" || estimate.match === "zone"
          ? "SAVED LANE"
          : "ESTIMATE";
  return (
    <aside className="landed-summary">
      <small>ESTIMATED LANDED COST</small>
      <div className="chip-row" role="group" aria-label="Freight basis">
        <Button variant="ghost" className={`filter-chip${basis === "standard" ? " is-active" : ""}`} onClick={() => onBasis("standard")}>Normal freight</Button>
        <Button variant="ghost" className={`filter-chip${basis === "distance" ? " is-active" : ""}`} onClick={() => onBasis("distance")}>Road distance</Button>
      </div>
      <strong>{shown?.landed ? formatMoney(shown.landed) : onRequest ? "Freight on request" : "—"}</strong>
      <p>{shown?.perUnit ? `${formatMoney(shown.perUnit)} / kg delivered` : onRequest ? (basis === "distance" ? "Road distance is unavailable" : "No Plenza freight rule for this lane") : "Choose a supplier and calculate"}</p>
      <div className="cost-lines">
        <span><small>Supplier asking price</small><strong>{supplier ? `${formatMoney(supplier.askingPrice)} / kg` : "—"}</strong></span>
        <span><small>Material</small><strong>{estimate ? formatMoney(estimate.materialValue) : "—"}</strong></span>
        <span><small>Freight{shown?.label ? ` · ${shown.label}` : ""}</small><strong>{shown ? line(shown.freight) : "—"}</strong></span>
        {basis === "distance" && estimate?.distanceRatePerKm && (
          <span><small>Rate per km</small><strong>{formatMoney({ amount: estimate.distanceRatePerKm, currency: estimate.materialValue.currency }, 4)} / km</strong></span>
        )}
        <span><small>Landed / kg</small><strong>{shown ? line(shown.perUnit) : "—"}</strong></span>
      </div>
      <div className="route-option">
        <Truck size={20}/>
        <div><strong>{supplier?.organisation ?? "Supplier"}</strong><small>{shown?.note ?? "Estimate only · not the negotiated price"}</small></div>
        <Badge tone={onRequest ? "warning" : "positive"}>{badge}</Badge>
      </div>
    </aside>
  );
}
