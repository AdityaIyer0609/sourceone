import { BarChart3, Check, Clock3, History, MessageSquareText, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Heading } from "../components/ui";
import { negotiationOffers } from "../mocks/data";

export function NegotiationsPage() {
  const [version, setVersion] = useState(3);
  return (
    <div className="page">
      <div className="page-heading"><div><small>NEGOTIATION ROOM · NEG-2025-0418</small><Heading level={1}>SS 304 CR Coil · 12,000 kg</Heading><p>Ardent Industries ↔ Zenith Metalworks</p></div><Badge tone="warning"><Clock3 size={14} /> Expires in 06h 24m</Badge></div>
      <div className="negotiation-layout">
        <section className="offer-main">
          <div className="offer-head"><div><div className="avatar avatar--square">ZM</div><span><strong>Zenith Metalworks</strong><small>Verified mill partner · Mumbai</small></span></div><Badge tone="positive">LATEST OFFER · V3</Badge></div>
          <div className="offer-price"><small>OFFERED RATE</small><strong>₹208.40<em>/ kg</em></strong><span className="positive">₹6.40 below live market</span></div>
          <div className="offer-terms">{[["Material value", "₹25,00,800"], ["Freight", "Included"], ["GST (18%)", "₹4,50,144"], ["Landed total", "₹29,50,944"], ["Credit terms", "30 days"], ["Dispatch", "Within 3 days"]].map(([label,value], index) => <div className={index === 3 ? "emphasis" : ""} key={label}><small>{label}</small><strong>{value}</strong></div>)}</div>
          <div className="offer-message"><MessageSquareText size={18} /><p>“We have optimized the slit plan and can extend this final rate for the full 12 MT quantity. Freight to Vadodara is included.”</p></div>
          <div className="offer-actions"><Button><Check size={17} /> Accept offer</Button><Button variant="dark">Send counter offer</Button><Button variant="secondary">Ask a question</Button></div>
          <p className="approval-note"><ShieldCheck size={15} /> Acceptance routes to your Level 2 purchase approval.</p>
        </section>
        <aside className="version-panel">
          <div className="section-title"><div><small>AUDIT TRAIL</small><Heading level={2}>Offer versions</Heading></div><History size={18} /></div>
          <div className="version-list">{negotiationOffers.map((offer) => <Button variant="ghost" className={`version-item ${version === offer.v ? "is-active" : ""}`} key={offer.v} onClick={() => setVersion(offer.v)}><span className="version-node">V{offer.v}</span><span><strong>{offer.note}</strong><small>{offer.time}</small><b>{offer.price}</b><small>{offer.credit} · Freight {offer.freight}</small></span></Button>)}</div>
          <div className="saving-callout"><span>You save vs. initial offer</span><strong>₹94,200</strong><small>3.63% negotiated saving</small></div>
        </aside>
      </div>
      <section className="benchmark-bar"><BarChart3 size={22}/><div><strong>Market benchmark</strong><small>Comparable SS 304 trades, Mumbai, today</small></div><span><small>LOW</small><strong>₹207.90</strong></span><div className="benchmark-scale"><i/><b>Your offer</b></div><span><small>HIGH</small><strong>₹217.10</strong></span></section>
    </div>
  );
}
