import { ChevronDown, FileText, SearchX, SlidersHorizontal } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { paths } from "../app/paths";
import { AsyncContent } from "../components/feedback/AsyncContent";
import { EmptyState } from "../components/feedback/EmptyState";
import { ProductCard } from "../components/product/ProductCard";
import { Badge, Button, Checkbox, Heading } from "../components/ui";
import { useProducts } from "../lib/api/useProducts";

export function CataloguePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const search = searchParams.get("q") ?? "";
  const market = searchParams.get("market");
  const { data: products = [], error, isLoading, reload } = useProducts();
  const filtered = products.filter((product) =>
    [product.name, product.category, product.subcategory ?? "", product.productCode, ...product.pricing.map((pricing) => pricing.market.label)]
      .join(" ").toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <div className="page">
      <div className="page-heading">
        <div><small>4,862 VERIFIED ITEMS</small><Heading level={1}>Industrial item master</Heading><p>Standardized specifications, live supply and auditable market rates.</p></div>
        <Button variant="secondary"><FileText size={17} /> Upload BOM</Button>
      </div>
      <div className="catalogue-toolbar">
        <div className="chip-row">
          {["All materials", "Metals", "Polymers", "Packaging", "Chemicals"].map((item, index) => <Button key={item} variant="ghost" className={`filter-chip ${index === 0 ? "is-active" : ""}`}>{item}</Button>)}
        </div>
        <Button variant="secondary"><SlidersHorizontal size={16} /> Filters <Badge>4</Badge></Button>
      </div>
      <div className="catalogue-layout">
        <aside className="filter-panel">
          <div><strong>Category</strong><ChevronDown size={16} /></div>
          {["Stainless steel", "Carbon steel", "Non-ferrous", "Pipes & tubes", "Polymers"].map((item, i) => <Checkbox key={item} label={item} defaultChecked={i < 2} count={[1284, 946, 468, 713, 534][i]} />)}
          <div><strong>Availability</strong><ChevronDown size={16} /></div>
          {["Ready stock", "Within 3 days", "On request"].map((item) => <Checkbox key={item} label={item} />)}
          <div><strong>Certification</strong><ChevronDown size={16} /></div>
          <div><strong>Dispatch market</strong><ChevronDown size={16} /></div>
        </aside>
        <section>
          <AsyncContent isLoading={isLoading && !products.length} error={error} onRetry={reload} loadingLabel="Loading catalogue…">
            <div className="result-meta"><span><strong>{filtered.length}</strong> matching items</span><Button variant="ghost">Sort: Recommended <ChevronDown size={15} /></Button></div>
            {filtered.length > 0 ? (
              <div className="catalogue-grid">
                {filtered.map((product) => <ProductCard key={product.productCode} product={product} market={market} onOpen={() => navigate(paths.productDetail(product.productCode) + (market ? `?market=${encodeURIComponent(market)}` : ""))} />)}
              </div>
            ) : (
              <EmptyState icon={SearchX} title="No matching items" message={search ? `Nothing in the item master matches “${search}”. Try a different grade, standard or SKU.` : "No catalogue products are available yet."} />
            )}
          </AsyncContent>
        </section>
      </div>
    </div>
  );
}
