import { ChevronDown, FileText, SearchX, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { paths } from "../app/paths";
import { AsyncContent } from "../components/feedback/AsyncContent";
import { EmptyState } from "../components/feedback/EmptyState";
import { ProductCard } from "../components/product/ProductCard";
import { Badge, Button, Checkbox, Heading } from "../components/ui";
import type { Product } from "../lib/api/products";
import { useProducts } from "../lib/api/useProducts";
import { titleCase } from "../lib/pricingFormat";

function counts(products: Product[], value: (product: Product) => string | null) {
  const totals = new Map<string, number>();
  for (const product of products) {
    const key = value(product);
    if (!key) continue;
    totals.set(key, (totals.get(key) ?? 0) + 1);
  }
  return [...totals.entries()].sort(([left], [right]) => left.localeCompare(right));
}

function toggle(current: string[], value: string) {
  return current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
}

export function CataloguePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const search = searchParams.get("q") ?? "";
  const market = searchParams.get("market");
  const categoryFromUrl = searchParams.get("category");
  const { data: products = [], error, isLoading, reload } = useProducts();
  const [pickedCategories, setPickedCategories] = useState<string[] | null>(null);
  const [subcategories, setSubcategories] = useState<string[]>([]);
  const [availability, setAvailability] = useState<string[]>([]);
  const selectedCategories = pickedCategories ?? (categoryFromUrl ? [categoryFromUrl] : []);
  const categories = counts(products, (product) => product.category);
  const subcategoryOptions = counts(products, (product) =>
    selectedCategories.length === 0 || selectedCategories.includes(product.category) ? product.subcategory : null,
  );
  const availabilityOptions = counts(products, (product) => product.availability);
  const activeFilters = selectedCategories.length + subcategories.length + availability.length;
  const filtered = products.filter((product) => {
    if (selectedCategories.length > 0 && !selectedCategories.includes(product.category)) return false;
    if (subcategories.length > 0 && !subcategories.includes(product.subcategory ?? "")) return false;
    if (availability.length > 0 && !availability.includes(product.availability)) return false;
    if (!search) return true;
    const haystack = [product.name, product.category, product.subcategory ?? "", product.productCode, product.description ?? "", ...product.pricing.map((pricing) => pricing.market.label)]
      .join(" ")
      .toLowerCase();
    return haystack.includes(search.toLowerCase());
  }).sort((left, right) => left.name.localeCompare(right.name) || left.productCode.localeCompare(right.productCode));

  const chooseCategory = (category: string | null) => {
    setPickedCategories(category ? [category] : []);
    setSubcategories([]);
  };

  return (
    <div className="page">
      <div className="page-heading">
        <div><small>{isLoading && products.length === 0 ? "LOADING CATALOGUE" : `${products.length} ACTIVE ITEMS`}</small><Heading level={1}>Industrial item master</Heading><p>Standardized specifications, live supply and auditable market rates.</p></div>
        <Button variant="secondary" aria-disabled="true" title="BOM upload is not part of the SourceOne catalogue."><FileText size={17} /> Upload BOM</Button>
      </div>
      <AsyncContent isLoading={isLoading && products.length === 0} error={error} onRetry={reload} loadingLabel="Loading catalogue…">
        <div className="catalogue-toolbar">
          <div className="chip-row">
            <Button variant="ghost" className={`filter-chip${selectedCategories.length === 0 ? " is-active" : ""}`} onClick={() => chooseCategory(null)}>All materials</Button>
            {categories.map(([category]) => (
              <Button key={category} variant="ghost" className={`filter-chip${selectedCategories.length === 1 && selectedCategories[0] === category ? " is-active" : ""}`} onClick={() => chooseCategory(category)}>{titleCase(category)}</Button>
            ))}
          </div>
          <Button variant="secondary" aria-disabled="true" title="Use the category, subcategory and availability filters."><SlidersHorizontal size={16} /> Filters {activeFilters > 0 && <Badge>{activeFilters}</Badge>}</Button>
        </div>
        <div className="catalogue-layout">
          <aside className="filter-panel">
            <div><strong>Category</strong><ChevronDown size={16} /></div>
            {categories.map(([category, count]) => (
              <Checkbox key={category} label={titleCase(category)} count={count} checked={selectedCategories.includes(category)} onChange={() => { setPickedCategories(toggle(selectedCategories, category)); setSubcategories([]); }} />
            ))}
            <div><strong>Subcategory</strong><ChevronDown size={16} /></div>
            {subcategoryOptions.length === 0 ? <small>Not specified</small> : subcategoryOptions.map(([subcategory, count]) => (
              <Checkbox key={subcategory} label={subcategory} count={count} checked={subcategories.includes(subcategory)} onChange={() => setSubcategories(toggle(subcategories, subcategory))} />
            ))}
            <div><strong>Availability</strong><ChevronDown size={16} /></div>
            {availabilityOptions.map(([state, count]) => (
              <Checkbox key={state} label={state === "available" ? "Benchmark live" : "Rate on request"} count={count} checked={availability.includes(state)} onChange={() => setAvailability(toggle(availability, state))} />
            ))}
            <div><strong>Certification</strong><ChevronDown size={16} /></div>
            <small>Not specified</small>
            <div><strong>Dispatch market</strong><ChevronDown size={16} /></div>
            <small>Not specified</small>
          </aside>
          <section>
            <div className="result-meta"><span><strong>{filtered.length}</strong> matching items</span><Button variant="ghost" aria-disabled="true" title="Items are listed by product name.">Sort: Name <ChevronDown size={15} /></Button></div>
            {filtered.length > 0 ? (
              <div className="catalogue-grid">
                {filtered.map((product) => <ProductCard key={product.productCode} product={product} market={market} onOpen={() => navigate(paths.productDetail(product.productCode) + (market ? `?market=${encodeURIComponent(market)}` : ""))} />)}
              </div>
            ) : (
              <EmptyState icon={SearchX} title="No matching items" message={search || activeFilters ? "No active SourceOne product matches this search or filter." : "No catalogue products are available yet."} />
            )}
          </section>
        </div>
      </AsyncContent>
    </div>
  );
}
