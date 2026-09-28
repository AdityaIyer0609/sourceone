import { ArrowLeft, ArrowRight, History, MapPin, Minus, Plus, ReceiptText, ShieldCheck, Star, Truck } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { paths } from "../app/paths";
import { AsyncContent } from "../components/feedback/AsyncContent";
import { Price } from "../components/market/Price";
import { Sparkline } from "../components/market/Sparkline";
import { OfferModal } from "../components/negotiation/OfferModal";
import { LandedCostPreviewModal } from "../components/product/LandedCostPreviewModal";
import { ProductVisual } from "../components/product/ProductVisual";
import { Badge, Button, Heading, Input } from "../components/ui";
import { getErrorMessage } from "../lib/api/client";
import { getMaterialEstimate, type BenchmarkSummary } from "../lib/api/pricing";
import { startNegotiation } from "../lib/api/negotiations";
import { getProduct, selectPricing } from "../lib/api/products";
import { useApiQuery } from "../lib/api/useApiQuery";
import { BENCHMARK_GLYPH, formatDate, formatMoney, formatPercent, movementDirection, sparklineValues } from "../lib/pricingFormat";

function useDebounced<T>(value: T, delayMs: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

function EstimateSummary({ benchmark, quantity }: { benchmark: BenchmarkSummary | null; quantity: number }) {
  const debouncedQuantity = useDebounced(quantity, 350);
  const valid = Number.isFinite(debouncedQuantity) && debouncedQuantity > 0;
  const estimate = useApiQuery(
    benchmark?.current && valid ? `estimate:${benchmark.seriesCode}:${debouncedQuantity}` : null,
    (signal) => getMaterialEstimate(benchmark?.seriesCode ?? "", debouncedQuantity, benchmark?.unit.code, signal),
  );
  const label = "Estimated material value at SourceOne benchmark";

  if (!benchmark?.current || estimate.data?.availability === "rate_on_request") {
    return <div className="cost-summary"><span>{label}</span><strong>Rate on request</strong><small>No valid SourceOne benchmark is in effect for this product.</small></div>;
  }
  if (!valid) {
    return <div className="cost-summary"><span>{label}</span><strong>—</strong><small>Enter a quantity greater than zero.</small></div>;
  }
  if (estimate.error) {
    return <div className="cost-summary"><span>{label}</span><strong>—</strong><small className="negative">{getErrorMessage(estimate.error)}</small></div>;
  }
  const data = estimate.data;
  const note = data?.freshnessState === "stale"
    ? `Informational only · based on a stale benchmark (as of ${formatDate(benchmark.current.freshness.asOfDate)})`
    : "Informational only · freight and GST not included";
  return (
    <div className="cost-summary">
      <span>{label}</span>
      <strong>{data?.amount ? formatMoney(data.amount, 2) : "…"}</strong>
      <small>{note}</small>
    </div>
  );
}

export function ProductDetailPage() {
  const navigate = useNavigate();
  const { sku = "" } = useParams();
  const [searchParams] = useSearchParams();
  const [quantity, setQuantity] = useState(5000);
  const [calculatorOpen, setCalculatorOpen] = useState(false);
  const [negotiateOpen, setNegotiateOpen] = useState(false);
  const { data: product, error, isLoading, reload } = useApiQuery(`product:${sku}`, (signal) => getProduct(sku, signal));
  const benchmark = product ? selectPricing(product, { market: searchParams.get("market"), currency: searchParams.get("currency") }) : null;
  const otherMarkets = product?.pricing.filter((pricing) => pricing !== benchmark).map((pricing) => pricing.market.label) ?? [];
  const direction = benchmark ? movementDirection(benchmark) : null;
  const stale = benchmark?.current?.freshness.state === "stale";
  return (
    <div className="page">
      <Button variant="ghost" className="back-link" onClick={() => navigate(paths.catalogue)}><ArrowLeft size={16} /> Back to catalogue</Button>
      <AsyncContent isLoading={isLoading && !product} error={error} onRetry={reload} loadingLabel="Loading product…">
        {product && (
          <div className="product-detail">
            <section className="product-gallery">
              <div className="product-gallery__main"><ProductVisual glyph={BENCHMARK_GLYPH} dark /><Badge tone="positive">VERIFIED SOURCE</Badge></div>
              <div className="thumb-row"><div><ProductVisual glyph={BENCHMARK_GLYPH} /></div><div><ProductVisual glyph="SHEET" /></div><div className="cert-thumb"><ShieldCheck size={24} /><span>MTC available</span></div></div>
            </section>
            <section className="product-info">
              <div className="eyebrow-row"><Badge>{product.category.toUpperCase()}</Badge><span>ITEM {product.productCode}</span><span><Star size={14} fill="currentColor" /> 4.8 (126)</span></div>
              <Heading level={1}>{product.name}</Heading>
              <p className="lead">{[product.subcategory, product.description].filter(Boolean).join(" · ")}</p>
              <div className="spec-strip"><span><small>THICKNESS</small><strong>0.8–3.0 mm</strong></span><span><small>WIDTH</small><strong>600–1,500 mm</strong></span><span><small>ORIGIN</small><strong>Domestic</strong></span><span><small>MOQ</small><strong>500 kg</strong></span></div>
              <div className="rate-module">
                <div>
                  <small>SOURCEONE BENCHMARK {stale ? <Badge tone="warning">STALE</Badge> : benchmark?.current && <span className="live-dot" />}</small>
                  <Price value={benchmark?.current?.value ?? null} uom={benchmark?.unit.label ?? product.uom.label} change={benchmark?.movement.state === "ok" ? benchmark.movement.percent : null} />
                  <p>
                    {benchmark?.current
                      ? `${benchmark.priceBasis.label} ${benchmark.market.label} · ${benchmark.taxBasis.label} · As of ${formatDate(benchmark.current.freshness.asOfDate)}`
                      : benchmark ? `${benchmark.market.label} · No valid benchmark is in effect · Rate on request` : "No SourceOne benchmark is mapped to this product · Rate on request"}
                    {otherMarkets.length > 0 && ` · Also benchmarked: ${otherMarkets.join(", ")}`}
                  </p>
                </div>
                <div className="rate-module__chart">
                  <Sparkline large down={direction === "down"} values={sparklineValues(benchmark?.sparkline.points ?? [])} />
                  <small>{direction && benchmark?.movement.percent != null ? `vs previous ${formatPercent(benchmark.movement.percent)}` : "No previous benchmark"}</small>
                </div>
                <Button variant="ghost" disabled={!benchmark} onClick={() => benchmark && navigate(`${paths.liveRates}?series=${encodeURIComponent(benchmark.seriesCode)}`)}><History size={16} /> Rate history</Button>
              </div>
              <div className="procure-box">
                <div className="quantity-field"><label>Required quantity</label><div><Button variant="ghost" onClick={() => setQuantity(Math.max(500, quantity - 500))}><Minus size={16} /></Button><Input value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} /><span>{product.uom.code}</span><Button variant="ghost" onClick={() => setQuantity(quantity + 500)}><Plus size={16} /></Button></div></div>
                <div className="delivery-field"><label>Delivery PIN</label><div><MapPin size={17} /><Input defaultValue="390020" /></div></div>
                <EstimateSummary benchmark={benchmark} quantity={quantity} />
                <Button onClick={() => setCalculatorOpen(true)}>Calculate landed cost <ArrowRight size={17} /></Button>
                <Button variant="secondary" onClick={() => setNegotiateOpen(true)}>Request negotiated rate</Button>
              </div>
              <div className="assurance-row"><span><ShieldCheck size={18} /><strong>Quality assured</strong><small>MTC & inspection</small></span><span><Truck size={18} /><strong>Dispatch in 48 hrs</strong><small>From verified stock</small></span><span><ReceiptText size={18} /><strong>Business credit</strong><small>Up to 45 days</small></span></div>
            </section>
          </div>
        )}
      </AsyncContent>
      <section className="detail-tabs"><div className="tabs"><Button variant="ghost" className="is-active">Specifications</Button><Button variant="ghost">Supply terms</Button><Button variant="ghost">Documents</Button><Button variant="ghost">Q&A</Button></div><div className="spec-grid">{[["Grade", "AISI 304 / EN 1.4301"], ["Standard", "ASTM A240"], ["Surface finish", "2B"], ["Edge", "Slit / Mill"], ["Coil ID", "508 mm"], ["Tolerance", "As per ASTM A480"]].map(([key, value]) => <div key={key}><small>{key}</small><strong>{value}</strong></div>)}</div></section>
      {negotiateOpen && product && (
        <OfferModal
          title="Start negotiation"
          productName={product.name}
          context={benchmark?.current
            ? `SourceOne benchmark (reference): ${formatMoney(benchmark.current.value)} / ${benchmark.unit.label} · ${benchmark.market.label} · As of ${formatDate(benchmark.current.freshness.asOfDate)}`
            : "No valid SourceOne benchmark · Rate on request"}
          currency={benchmark?.currency ?? "INR"}
          uom={product.uom.code}
          initialQuantity={String(quantity)}
          submitLabel="Submit offer"
          onClose={() => setNegotiateOpen(false)}
          onSubmit={async (input) => {
            const negotiation = await startNegotiation({
              ...input,
              productCode: product.productCode,
              seriesCode: benchmark?.seriesCode,
              currency: benchmark ? undefined : "INR",
            });
            navigate(`${paths.negotiations}?id=${encodeURIComponent(negotiation.id)}`);
          }}
        />
      )}
      <LandedCostPreviewModal
        open={calculatorOpen}
        onClose={() => setCalculatorOpen(false)}
        onOpenCalculator={() => { setCalculatorOpen(false); navigate(paths.freightCalculator); }}
      />
    </div>
  );
}
