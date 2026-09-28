import { Heart } from "lucide-react";
import type { Product } from "../../mocks/data";
import { Price } from "../market/Price";
import { Badge, Button, Heading } from "../ui";
import { ProductVisual } from "./ProductVisual";

export function ProductCard({ product, onOpen }: { product: Product; onOpen: () => void }) {
  return (
    <article className="product-card" onClick={onOpen}>
      <ProductVisual glyph={product.glyph} />
      <div className="product-card__body">
        <div className="product-card__meta"><Badge>{product.category}</Badge><Button variant="ghost" className="icon-button" aria-label="Save item"><Heart size={17} /></Button></div>
        <Heading level={3}>{product.name}</Heading>
        <p>{product.id} · BIS verified</p>
        <Price value={product.price} uom={product.uom} change={product.change} />
        <div className="product-card__foot"><span><span className="stock-dot" />{product.stock}</span><span>{product.city}</span></div>
      </div>
    </article>
  );
}
