import { ArrowLeft, ArrowRight, History, MapPin, Minus, Plus, ReceiptText, ShieldCheck, Truck } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { paths } from "../app/paths";
import { AsyncContent } from "../components/feedback/AsyncContent";
import { EmptyState } from "../components/feedback/EmptyState";
import { Price } from "../components/market/Price";
import { OfferModal } from "../components/negotiation/OfferModal";
import { LandedCostPreviewModal } from "../components/product/LandedCostPreviewModal";
import { ProductCard } from "../components/product/ProductCard";
import { ProductVisual } from "../components/product/ProductVisual";
import { Badge, Button, Heading, Input } from "../components/ui";
import { getErrorMessage } from "../lib/api/client";
import { getMaterialEstimate, type BenchmarkSummary } from "../lib/api/pricing";
import { listProductListings } from "../lib/api/listings";
import { startNegotiation } from "../lib/api/negotiations";
import { getProduct, listProducts, selectPricing } from "../lib/api/products";
import { answerProductQuestion, askProductQuestion, downloadProductDocument, listProductDocuments, listProductQuestions } from "../lib/api/productContent";
import { useApiQuery } from "../lib/api/useApiQuery";
import { BENCHMARK_GLYPH, formatDate, formatMoney, formatPercent, movementDirection, titleCase } from "../lib/pricingFormat";

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
  const label = "Estimated material value at Plenza benchmark";

  if (!benchmark?.current || estimate.data?.availability === "rate_on_request") {
    return <div className="cost-summary"><span>{label}</span><strong>Rate on request</strong><small>No valid Plenza benchmark is in effect for this product.</small></div>;
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
  const [destinationPin, setDestinationPin] = useState("");
  const [calculatorOpen, setCalculatorOpen] = useState(false);
  const [negotiateOpen, setNegotiateOpen] = useState(false);
  const [tab, setTab] = useState<"specifications" | "supply" | "documents" | "questions">("specifications");
  const [question, setQuestion] = useState("");
  const [replies, setReplies] = useState<Record<string, string>>({});
  const [contentError, setContentError] = useState<string | null>(null);
  const { data: product, error, isLoading, reload } = useApiQuery(`product:${sku}`, (signal) => getProduct(sku, signal));
  const benchmark = product ? selectPricing(product, { market: searchParams.get("market"), currency: searchParams.get("currency") }) : null;
  const listings = useApiQuery(
    product ? `listings:${product.productCode}:${benchmark?.currency ?? ""}` : null,
    (signal) => listProductListings(product?.productCode ?? "", benchmark?.currency, signal),
  );
  const offers = (listings.data ?? []).map((listing) => ({
    id: listing.supplierUserId,
    name: listing.supplierName,
    organisation: listing.organisation,
    askingPrice: listing.askingPrice.amount,
    originPin: listing.originPin,
    originLabel: listing.originLabel,
    minimumQuantity: listing.minimumQuantity,
    availability: listing.availability,
  }));
  const moq = offers.length ? `${Number(Math.min(...offers.map((offer) => Number(offer.minimumQuantity)))).toLocaleString("en-IN")} ${product?.uom.code.toLowerCase()}` : "—";
  const documents = useApiQuery(product ? `documents:${product.productCode}` : null, (signal) => listProductDocuments(product?.productCode ?? "", signal));
  const questionList = useApiQuery(product ? `questions:${product.productCode}` : null, (signal) => listProductQuestions(product?.productCode ?? "", signal));
  const related = useApiQuery(
    product ? `related:${product.category}:${product.productCode}` : null,
    (signal) => listProducts({ category: product?.category }, signal),
  );
  const relatedProducts = (related.data ?? []).filter((item) => item.productCode !== product?.productCode);
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
              <div className="product-gallery__main"><ProductVisual glyph={BENCHMARK_GLYPH} dark /><Badge tone={product.availability === "available" ? "positive" : "neutral"}>{product.availability === "available" ? "BENCHMARK LIVE" : "RATE ON REQUEST"}</Badge></div>
              <div className="thumb-row"><div><ProductVisual glyph={BENCHMARK_GLYPH} /></div><div><ProductVisual glyph={BENCHMARK_GLYPH} /></div><div className="cert-thumb"><ShieldCheck size={24} /><span>{product.listingCount} {product.listingCount === 1 ? "supplier" : "suppliers"}</span></div></div>
            </section>
            <section className="product-info">
              <div className="eyebrow-row"><Badge>{product.category.toUpperCase()}</Badge><span>ITEM {product.productCode}</span><span>{product.listingCount} {product.listingCount === 1 ? "supplier" : "suppliers"}</span></div>
              <Heading level={1}>{product.name}</Heading>
              <p className="lead">{[product.subcategory, product.description].filter(Boolean).join(" · ")}</p>
              <div className="spec-strip">{(["grade", "mfi", "density"] as const).map((key) => {
                const field = product.specifications.find((item) => item.key === key);
                return <span key={key}><small>{field?.label ?? key}</small><strong>{field?.value ?? "Not specified"}</strong></span>;
              })}<span><small>MOQ</small><strong>{moq}</strong></span></div>
              {offers.length > 0 && <div className="spec-strip">{offers.map((offer) => <span key={offer.id}><small>{offer.organisation} · {titleCase(offer.availability ?? "")}</small><strong>Asking {formatMoney({ amount: offer.askingPrice ?? "0", currency: benchmark?.currency ?? "INR" })} · MOQ {Number(offer.minimumQuantity).toLocaleString("en-IN")}</strong></span>)}</div>}
              <div className="rate-module">
                <small>PLENZA BENCHMARK {stale ? <Badge tone="warning">STALE</Badge> : benchmark?.current && <span className="live-dot" />}</small>
                <div className="rate-module__row">
                  <Price value={benchmark?.current?.value ?? null} uom={benchmark?.unit.label ?? product.uom.label} change={benchmark?.movement.state === "ok" ? benchmark.movement.percent : null} />
                  <small>{direction && benchmark?.movement.percent != null ? `vs previous ${formatPercent(benchmark.movement.percent)}` : "No previous benchmark"}</small>
                </div>
                <p>
                  {benchmark?.current
                    ? `${benchmark.priceBasis.label} ${benchmark.market.label} · ${benchmark.taxBasis.label} · As of ${formatDate(benchmark.current.freshness.asOfDate)}`
                    : benchmark ? `${benchmark.market.label} · No valid benchmark is in effect · Rate on request` : "No Plenza benchmark is mapped to this product · Rate on request"}
                  {otherMarkets.length > 0 && ` · Also benchmarked: ${otherMarkets.join(", ")}`}
                </p>
                <Button variant="ghost" disabled={!benchmark} onClick={() => benchmark && navigate(`${paths.liveRates}?series=${encodeURIComponent(benchmark.seriesCode)}`)}><History size={16} /> Rate history</Button>
              </div>
              <div className="procure-box">
                <div className="quantity-field"><label>Required quantity</label><div><Button variant="ghost" onClick={() => setQuantity(Math.max(500, quantity - 500))}><Minus size={16} /></Button><Input value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} /><span>{product.uom.code}</span><Button variant="ghost" onClick={() => setQuantity(quantity + 500)}><Plus size={16} /></Button></div></div>
                <div className="delivery-field"><label>Delivery PIN</label><div><MapPin size={17} /><Input value={destinationPin} onChange={(event) => setDestinationPin(event.target.value)} /></div></div>
                <EstimateSummary benchmark={benchmark} quantity={quantity} />
                <Button onClick={() => setCalculatorOpen(true)}>Calculate landed cost <ArrowRight size={17} /></Button>
                <Button variant="secondary" disabled={offers.length === 0} title={offers.length === 0 ? "No supplier is listing this product" : undefined} onClick={() => setNegotiateOpen(true)}>Request negotiated rate</Button>
                <Button variant="secondary" onClick={() => navigate(`${paths.purchaseRequests}?product=${encodeURIComponent(product.productCode)}&quantity=${encodeURIComponent(String(quantity))}&pin=${encodeURIComponent(destinationPin)}`)}>Create purchase request</Button>
              </div>
              <div className="assurance-row"><span><ShieldCheck size={18} /><strong>{product.listingCount} {product.listingCount === 1 ? "supplier" : "suppliers"}</strong><small>Active listings</small></span><span><Truck size={18} /><strong>{product.availability === "available" ? "Benchmark live" : "Rate on request"}</strong><small>{benchmark?.current ? `As of ${formatDate(benchmark.current.freshness.asOfDate)}` : "No current benchmark"}</small></span><span><ReceiptText size={18} /><strong>{offers.length ? "Listed" : "No listing"}</strong><small>{offers.length ? `${offers.length} eligible in this currency` : "No supplier is listing this product"}</small></span></div>
            </section>
          </div>
        )}
      </AsyncContent>
      {product && (
        <>
          <section className="detail-tabs">
            <div className="tabs">
              <Button variant="ghost" className={tab === "specifications" ? "is-active" : ""} onClick={() => setTab("specifications")}>Specifications</Button>
              <Button variant="ghost" className={tab === "supply" ? "is-active" : ""} onClick={() => setTab("supply")}>Supply terms</Button>
              <Button variant="ghost" className={tab === "documents" ? "is-active" : ""} onClick={() => setTab("documents")}>Documents</Button>
              <Button variant="ghost" className={tab === "questions" ? "is-active" : ""} onClick={() => setTab("questions")}>Q&A</Button>
            </div>
            {tab === "specifications" && <div className="spec-grid">{product.specifications.map((field) => <div key={field.key} className={field.key === "description" ? "spec-grid__wide" : undefined}><small>{field.label}</small><strong>{field.value ?? "Not specified"}</strong></div>)}</div>}
            {tab === "supply" && (offers.length > 0 ? <div className="spec-grid">{offers.map((offer) => <div key={offer.id}><small>{offer.organisation} · {titleCase(offer.availability ?? "")}</small><strong>Asking {formatMoney({ amount: offer.askingPrice ?? "0", currency: benchmark?.currency ?? "INR" })} · MOQ {Number(offer.minimumQuantity).toLocaleString("en-IN")} {product.uom.code}</strong></div>)}</div> : <EmptyState title="No active listings" message="No supplier is listing this product." />)}
            {tab === "documents" && (
              <AsyncContent isLoading={documents.isLoading && !documents.data} error={documents.error} onRetry={documents.reload} isEmpty={!documents.isLoading && !documents.error && (documents.data ?? []).length === 0} emptyTitle="No documents" emptyMessage="No documents are on file for this product." loadingLabel="Loading documents…">
                <div className="spec-grid">{(documents.data ?? []).map((document) => <div key={document.id}><small>{document.documentType}</small><strong>{document.name}</strong><Button variant="ghost" onClick={() => void downloadProductDocument(product.productCode, document.id, document.filename).catch((cause) => setContentError(getErrorMessage(cause)))}>Download</Button></div>)}</div>
              </AsyncContent>
            )}
            {tab === "questions" && (
              <AsyncContent isLoading={questionList.isLoading && !questionList.data} error={questionList.error} onRetry={questionList.reload} loadingLabel="Loading questions…">
                {(questionList.data?.questions.length ?? 0) === 0 && <EmptyState title="No questions" message="No questions have been asked about this product." />}
                <div className="spec-grid">{(questionList.data?.questions ?? []).map((item) => <div key={item.id}><small>{item.organisation} · {titleCase(item.status)}</small><strong>{item.body}</strong>{item.answers.map((answer) => <p key={answer.id}><small>{answer.organisation}</small> {answer.body}</p>)}{questionList.data?.canAnswer && <label>Reply<Input value={replies[item.id] ?? ""} onChange={(event) => setReplies({ ...replies, [item.id]: event.target.value })} /></label>}{questionList.data?.canAnswer && <Button variant="secondary" disabled={!(replies[item.id] ?? "").trim()} onClick={() => void answerProductQuestion(product.productCode, item.id, replies[item.id] ?? "").then(() => { setReplies({ ...replies, [item.id]: "" }); questionList.reload(); }).catch((cause) => setContentError(getErrorMessage(cause)))}>Answer</Button>}</div>)}</div>
                {questionList.data?.canAsk && <div className="form-grid"><label>Ask a question<Input value={question} onChange={(event) => setQuestion(event.target.value)} /></label><Button disabled={!question.trim()} onClick={() => void askProductQuestion(product.productCode, question).then(() => { setQuestion(""); questionList.reload(); }).catch((cause) => setContentError(getErrorMessage(cause)))}>Ask</Button></div>}
              </AsyncContent>
            )}
            {contentError && <p className="negative">{contentError}</p>}
          </section>
          <section className="section-block">
            <div className="section-title"><div><small>SAME CATEGORY</small><Heading level={2}>Related products</Heading></div></div>
            <AsyncContent isLoading={related.isLoading && !related.data} error={related.error} onRetry={related.reload} isEmpty={!related.isLoading && !related.error && relatedProducts.length === 0} emptyTitle="No related products" emptyMessage="No other active product is in this category." loadingLabel="Loading related products…">
              <div className="product-row">
                {relatedProducts.map((item) => <ProductCard key={item.productCode} product={item} onOpen={() => navigate(paths.productDetail(item.productCode))} />)}
              </div>
            </AsyncContent>
          </section>
        </>
      )}
      {negotiateOpen && product && (
        <OfferModal
          title="Start negotiation"
          productName={product.name}
          context={benchmark?.current
            ? `Plenza benchmark (reference): ${formatMoney(benchmark.current.value)} / ${benchmark.unit.label} · ${benchmark.market.label} · As of ${formatDate(benchmark.current.freshness.asOfDate)}`
            : "No valid Plenza benchmark · Rate on request"}
          currency={benchmark?.currency ?? "INR"}
          uom={product.uom.code}
          initialQuantity={String(quantity)}
          submitLabel="Submit offer"
          suppliers={offers}
          onClose={() => setNegotiateOpen(false)}
          onSubmit={async (input) => {
            const negotiation = await startNegotiation({
              ...input,
              supplierUserId: input.supplierUserId,
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
        productName={product?.name ?? ""}
        productCode={product?.productCode ?? ""}
        quantity={quantity}
        uom={product?.uom.code ?? "KG"}
        destinationPin={destinationPin}
        suppliers={offers}
        onClose={() => setCalculatorOpen(false)}
        onOpenCalculator={() => { setCalculatorOpen(false); navigate(paths.freightCalculator); }}
      />
    </div>
  );
}
