import { ArrowRight, ChevronDown, ChevronRight, MessageSquareText, ReceiptText, RefreshCw, Truck, type LucideIcon } from "lucide-react";
import { Fragment } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { paths } from "../app/paths";
import { AsyncContent } from "../components/feedback/AsyncContent";
import { MarketTable } from "../components/market/MarketTable";
import { ProductCard } from "../components/product/ProductCard";
import { ProductVisual } from "../components/product/ProductVisual";
import { Badge, Button, Heading } from "../components/ui";
import { listProducts } from "../lib/api/products";
import { useApiQuery } from "../lib/api/useApiQuery";
import { useBenchmarks } from "../lib/api/useBenchmarks";
import { formatMoney, formatPercent, movementDirection, titleCase } from "../lib/pricingFormat";
const heroImage =
  "https://images.unsplash.com/photo-1697698532634-ea59b636ccea?crop=entropy&cs=tinysrgb&fit=crop&fm=jpg&q=86&w=1600";

const shortcuts: { icon: LucideIcon; title: string; note: string; to: string }[] = [
  { icon: ReceiptText, title: "Create purchase request", note: "Ask an eligible supplier for a product", to: paths.purchaseRequests },
  { icon: Truck, title: "Calculate landed cost", note: "PIN-to-PIN freight in seconds", to: paths.freightCalculator },
  { icon: MessageSquareText, title: "Review open offers", note: "Open negotiations waiting on you", to: paths.negotiations },
  { icon: RefreshCw, title: "Reorder from history", note: "Repeat with current market rates", to: paths.reorder },
];

function catalogueLink(search: string) {
  return search ? `${paths.catalogue}?${new URLSearchParams({ q: search })}` : paths.catalogue;
}

function categoryGlyph(category: string) {
  return category.replace(/[^a-z0-9]/gi, "").slice(0, 4).toUpperCase() || "ITEM";
}

export function MarketplacePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const search = searchParams.get("q") ?? "";
  const { data: benchmarks = [], error: benchmarkError, isLoading: benchmarksLoading, reload: reloadBenchmarks } = useBenchmarks();
  const catalogue = useApiQuery(`marketplace:${search}`, (signal) =>
    listProducts({ q: search || undefined }, signal),
  );
  const products = catalogue.data ?? [];
  const rail = useApiQuery("marketplace-categories", (signal) => listProducts({}, signal));
  const materials = [...(rail.data ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  const liveCount = benchmarks.filter((benchmark) => benchmark.availability === "available").length;
  const ticker = benchmarks.filter((benchmark) => benchmark.current).slice(0, 3);
  return (
    <div className="page page--market">
      <section className="hero">
        <img src={heroImage} alt="Industrial warehouse" />
        <div className="hero__scrim" />
        <div className="hero__content">
          <Badge tone="positive"><span className="live-dot" /> {liveCount} benchmarks live now</Badge>
          <Heading level={1}>Materials move faster<br />when markets are clear.</Heading>
          <p>Source verified industrial materials, compare live rates, and calculate landed cost before you commit.</p>
          <div className="hero__actions">
            <Button onClick={() => navigate(paths.catalogue)}>Explore item master <ArrowRight size={17} /></Button>
            <Button variant="secondary" onClick={() => navigate(paths.liveRates)}>View live rates</Button>
          </div>
        </div>
        <div className="hero__ticker">
          {ticker.map((benchmark, index) => {
            const direction = movementDirection(benchmark);
            return (
              <Fragment key={benchmark.seriesCode}>
                {index > 0 && <i />}
                <span>{benchmark.name.toUpperCase()}</span><strong>{benchmark.current && formatMoney(benchmark.current.value)}</strong>
                {direction && benchmark.movement.percent !== null && <em className={direction === "down" ? "negative" : "positive"}>{formatPercent(benchmark.movement.percent)}</em>}
              </Fragment>
            );
          })}
        </div>
      </section>

      <section className="section-block">
        <div className="section-title"><div><small>ITEM MASTER</small><Heading level={2}>Source by material</Heading></div><Button variant="ghost" onClick={() => navigate(catalogueLink(search))}>View all {rail.data?.length ?? 0} items <ArrowRight size={16} /></Button></div>
        <AsyncContent isLoading={rail.isLoading && !rail.data} error={rail.error} onRetry={rail.reload} isEmpty={!rail.isLoading && !rail.error && materials.length === 0} emptyTitle="No active products" emptyMessage="The Plenza catalogue has no active products yet." loadingLabel="Loading catalogue…">
          <div className="category-rail">
            {materials.map((product) => (
              <Button variant="ghost" className="category-tile" key={product.productCode} onClick={() => navigate(paths.productDetail(product.productCode))}>
                <ProductVisual glyph={categoryGlyph(product.productCode)} /><span><strong>{product.name}</strong><small>{titleCase(product.category)}</small><small>{product.subcategory}</small></span><ArrowRight size={17} />
              </Button>
            ))}
          </div>
        </AsyncContent>
      </section>

      <div className="market-grid">
        <section className="section-block rates-panel">
          <div className="section-title"><div><small>MARKET PULSE</small><Heading level={2}>Live benchmark rates <Badge tone="positive"><span className="live-dot" /> LIVE</Badge></Heading></div><Button variant="ghost" onClick={() => navigate(paths.liveRates)}>Open rate desk <ArrowRight size={16} /></Button></div>
          <AsyncContent isLoading={benchmarksLoading && !benchmarks.length} error={benchmarkError} onRetry={reloadBenchmarks} isEmpty={!benchmarks.length} emptyTitle="No benchmarks yet" loadingLabel="Loading Plenza benchmarks…">
            <MarketTable compact benchmarks={benchmarks} onSelect={(code) => navigate(`${paths.liveRates}?series=${encodeURIComponent(code)}`)} />
          </AsyncContent>
        </section>
        <section className="section-block action-panel">
          <div className="section-title"><div><small>SHORTCUTS</small><Heading level={2}>Move to action</Heading></div></div>
          {shortcuts.map(({ icon: Icon, title, note, to }) => (
            <Button variant="ghost" className="action-row" key={title} onClick={() => navigate(to)}><span className="action-row__icon"><Icon size={19} /></span><span><strong>{title}</strong><small>{note}</small></span><ChevronRight size={17} /></Button>
          ))}
        </section>
      </div>

      <section className="section-block">
        <div className="section-title"><div><small>PLENZA CATALOGUE</small><Heading level={2}>Active products</Heading></div><Button variant="ghost" onClick={() => navigate(catalogueLink(search))}>View catalogue <ChevronDown size={15} /></Button></div>
        <AsyncContent isLoading={catalogue.isLoading && !catalogue.data} error={catalogue.error} onRetry={catalogue.reload} isEmpty={!catalogue.isLoading && !catalogue.error && products.length === 0} emptyTitle="No matching products" emptyMessage={search ? "No active Plenza product matches this search." : "The Plenza catalogue has no active products yet."} loadingLabel="Loading products…">
          <div className="product-row">
            {products.map((product) => <ProductCard key={product.productCode} product={product} onOpen={() => navigate(paths.productDetail(product.productCode))} />)}
          </div>
        </AsyncContent>
      </section>
    </div>
  );
}
