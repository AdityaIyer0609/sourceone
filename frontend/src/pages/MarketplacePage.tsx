import { ArrowRight, ChevronDown, ChevronRight, MessageSquareText, ReceiptText, RefreshCw, Truck, type LucideIcon } from "lucide-react";
import { Fragment } from "react";
import { useNavigate } from "react-router-dom";
import { paths } from "../app/paths";
import { AsyncContent } from "../components/feedback/AsyncContent";
import { MarketTable } from "../components/market/MarketTable";
import { ProductCard } from "../components/product/ProductCard";
import { ProductVisual } from "../components/product/ProductVisual";
import { Badge, Button, Heading } from "../components/ui";
import { useBenchmarks } from "../lib/api/useBenchmarks";
import { useProducts } from "../lib/api/useProducts";
import { formatMoney, formatPercent, movementDirection } from "../lib/pricingFormat";
import { heroImage, marketplaceCategories } from "../mocks/data";

const shortcuts: { icon: LucideIcon; title: string; note: string; to: string }[] = [
  { icon: ReceiptText, title: "Create purchase request", note: "Multi-item RFQ with approval routing", to: paths.freightCalculator },
  { icon: Truck, title: "Calculate landed cost", note: "PIN-to-PIN freight in seconds", to: paths.freightCalculator },
  { icon: MessageSquareText, title: "Review open offers", note: "3 supplier updates need review", to: paths.negotiations },
  { icon: RefreshCw, title: "Reorder from history", note: "Repeat with current market rates", to: paths.reorder },
];

export function MarketplacePage() {
  const navigate = useNavigate();
  const { data: benchmarks = [], error, isLoading, reload } = useBenchmarks();
  const { data: products = [] } = useProducts();
  const liveCount = benchmarks.filter((benchmark) => benchmark.availability === "available").length;
  const ticker = benchmarks.filter((benchmark) => benchmark.current).slice(0, 3);
  return (
    <div className="page page--market">
      <section className="hero">
        <img src={heroImage} alt="Steel coils stored in a modern industrial warehouse" />
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
        <div className="section-title"><div><small>ITEM MASTER</small><Heading level={2}>Source by material</Heading></div><Button variant="ghost" onClick={() => navigate(paths.catalogue)}>View all 4,862 items <ArrowRight size={16} /></Button></div>
        <div className="category-rail">
          {marketplaceCategories.map(([glyph, name, count]) => (
            <Button variant="ghost" className="category-tile" key={name} onClick={() => navigate(paths.catalogue)}>
              <ProductVisual glyph={glyph} /><span><strong>{name}</strong><small>{count}</small></span><ArrowRight size={17} />
            </Button>
          ))}
        </div>
      </section>

      <div className="market-grid">
        <section className="section-block rates-panel">
          <div className="section-title"><div><small>MARKET PULSE</small><Heading level={2}>Live benchmark rates <Badge tone="positive"><span className="live-dot" /> LIVE</Badge></Heading></div><Button variant="ghost" onClick={() => navigate(paths.liveRates)}>Open rate desk <ArrowRight size={16} /></Button></div>
          <AsyncContent isLoading={isLoading && !benchmarks.length} error={error} onRetry={reload} isEmpty={!benchmarks.length} emptyTitle="No benchmarks yet" loadingLabel="Loading SourceOne benchmarks…">
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
        <div className="section-title"><div><small>CURATED FOR ARDENT</small><Heading level={2}>Frequently procured</Heading></div><Button variant="ghost">Based on 90-day activity <ChevronDown size={15} /></Button></div>
        <div className="product-row">
          {products.slice(0, 4).map((product) => <ProductCard key={product.productCode} product={product} onOpen={() => navigate(paths.productDetail(product.productCode))} />)}
        </div>
      </section>
    </div>
  );
}
