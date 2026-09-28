import { ArrowLeft, ArrowRight, History, MapPin, Minus, Plus, ReceiptText, ShieldCheck, Star, Truck } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { paths } from "../app/paths";
import { Price } from "../components/market/Price";
import { Sparkline } from "../components/market/Sparkline";
import { LandedCostPreviewModal } from "../components/product/LandedCostPreviewModal";
import { ProductVisual } from "../components/product/ProductVisual";
import { Badge, Button, Heading, Input } from "../components/ui";
import { products } from "../mocks/data";

export function ProductDetailPage() {
  const navigate = useNavigate();
  const [quantity, setQuantity] = useState(5000);
  const [calculatorOpen, setCalculatorOpen] = useState(false);
  const subtotal = quantity * products[0].price;
  return (
    <div className="page">
      <Button variant="ghost" className="back-link" onClick={() => navigate(paths.catalogue)}><ArrowLeft size={16} /> Back to catalogue</Button>
      <div className="product-detail">
        <section className="product-gallery">
          <div className="product-gallery__main"><ProductVisual glyph="COIL" dark /><Badge tone="positive">VERIFIED SOURCE</Badge></div>
          <div className="thumb-row"><div><ProductVisual glyph="COIL" /></div><div><ProductVisual glyph="SHEET" /></div><div className="cert-thumb"><ShieldCheck size={24} /><span>MTC available</span></div></div>
        </section>
        <section className="product-info">
          <div className="eyebrow-row"><Badge>STAINLESS STEEL</Badge><span>SKU CR-304-2B</span><span><Star size={14} fill="currentColor" /> 4.8 (126)</span></div>
          <Heading level={1}>SS 304 Cold Rolled Coil</Heading>
          <p className="lead">ASTM A240 · 2B finish · Prime material · Slit edge</p>
          <div className="spec-strip"><span><small>THICKNESS</small><strong>0.8–3.0 mm</strong></span><span><small>WIDTH</small><strong>600–1,500 mm</strong></span><span><small>ORIGIN</small><strong>Domestic</strong></span><span><small>MOQ</small><strong>500 kg</strong></span></div>
          <div className="rate-module">
            <div><small>LIVE TRADE RATE <span className="live-dot" /></small><Price value={214.8} uom="kg" change={1.24} /><p>Ex-works Mumbai · GST extra</p></div>
            <div className="rate-module__chart"><Sparkline large /><small>7D +3.8%</small></div>
            <Button variant="ghost"><History size={16} /> Rate history</Button>
          </div>
          <div className="procure-box">
            <div className="quantity-field"><label>Required quantity</label><div><Button variant="ghost" onClick={() => setQuantity(Math.max(500, quantity - 500))}><Minus size={16} /></Button><Input value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} /><span>KG</span><Button variant="ghost" onClick={() => setQuantity(quantity + 500)}><Plus size={16} /></Button></div></div>
            <div className="delivery-field"><label>Delivery PIN</label><div><MapPin size={17} /><Input defaultValue="390020" /></div></div>
            <div className="cost-summary"><span>Material value</span><strong>₹{subtotal.toLocaleString("en-IN")}</strong><small>Freight calculated next</small></div>
            <Button onClick={() => setCalculatorOpen(true)}>Calculate landed cost <ArrowRight size={17} /></Button>
            <Button variant="secondary">Request negotiated rate</Button>
          </div>
          <div className="assurance-row"><span><ShieldCheck size={18} /><strong>Quality assured</strong><small>MTC & inspection</small></span><span><Truck size={18} /><strong>Dispatch in 48 hrs</strong><small>From verified stock</small></span><span><ReceiptText size={18} /><strong>Business credit</strong><small>Up to 45 days</small></span></div>
        </section>
      </div>
      <section className="detail-tabs"><div className="tabs"><Button variant="ghost" className="is-active">Specifications</Button><Button variant="ghost">Supply terms</Button><Button variant="ghost">Documents</Button><Button variant="ghost">Q&A</Button></div><div className="spec-grid">{[["Grade", "AISI 304 / EN 1.4301"], ["Standard", "ASTM A240"], ["Surface finish", "2B"], ["Edge", "Slit / Mill"], ["Coil ID", "508 mm"], ["Tolerance", "As per ASTM A480"]].map(([key, value]) => <div key={key}><small>{key}</small><strong>{value}</strong></div>)}</div></section>
      <LandedCostPreviewModal
        open={calculatorOpen}
        onClose={() => setCalculatorOpen(false)}
        onOpenCalculator={() => { setCalculatorOpen(false); navigate(paths.freightCalculator); }}
      />
    </div>
  );
}
