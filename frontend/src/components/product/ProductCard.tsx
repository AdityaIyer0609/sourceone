import { Heart } from "lucide-react";
import { selectPricing, type Product } from "../../lib/api/products";
import { BENCHMARK_GLYPH, formatDate, titleCase } from "../../lib/pricingFormat";
import { Price } from "../market/Price";
import { Badge, Button, Heading } from "../ui";
import { ProductVisual } from "./ProductVisual";

export function ProductCard({ product, market, onOpen }: { product: Product; market?: string | null; onOpen: () => void }) {
  const pricing = selectPricing(product, { market });
  const current = pricing?.current ?? null;
  const asOf = current
    ? `As of ${formatDate(current.freshness.asOfDate)}${current.freshness.state === "stale" ? " · Stale" : ""}`
    : "No current benchmark";
  return (
    <article className="product-card" onClick={onOpen}>
      <ProductVisual glyph={BENCHMARK_GLYPH} />
      <div className="product-card__body">
        <div className="product-card__meta"><Badge>{titleCase(product.category)}</Badge><Button variant="ghost" className="icon-button" aria-label="Save item"><Heart size={17} /></Button></div>
        <Heading level={3}>{product.name}</Heading>
        <p>{product.productCode}{product.subcategory ? ` · ${product.subcategory}` : ""} · {product.uom.label}</p>
        <Price value={current?.value ?? null} uom={pricing?.unit.label ?? product.uom.label} change={pricing?.movement.state === "ok" ? pricing.movement.percent : null} />
        <div className="product-card__foot"><span><span className="stock-dot" />{product.availability === "available" ? asOf : "Rate on request"}</span><span>{product.listingCount} {product.listingCount === 1 ? "supplier" : "suppliers"}</span></div>
      </div>
    </article>
  );
}
