import { Plus } from "lucide-react";
import { MarketTable } from "../components/market/MarketTable";
import { Sparkline } from "../components/market/Sparkline";
import { Badge, Button, Heading } from "../components/ui";

export function LiveRatesPage() {
  return (
    <div className="page">
      <div className="page-heading">
        <div><small>MARKET INTELLIGENCE</small><Heading level={1}>Live rate desk</Heading><p>Auditable benchmark pricing across primary industrial material markets.</p></div>
        <div className="market-open"><span className="live-dot" /><div><strong>Markets open</strong><small>Last refresh 8 sec ago</small></div></div>
      </div>
      <div className="index-strip">
        {[["METALS INDEX", "128.42", "+1.18%"], ["POLYMER INDEX", "94.08", "+0.42%"], ["FERROUS", "82.17", "−0.31%"], ["NON-FERROUS", "144.62", "+2.04%"]].map(([name, value, change]) => <div key={name}><small>{name}</small><strong>{value}</strong><span className={change.startsWith("−") ? "negative" : "positive"}>{change}</span><Sparkline down={change.startsWith("−")} /></div>)}
      </div>
      <section className="rate-chart-panel">
        <div className="section-title"><div><Badge>STAINLESS STEEL</Badge><Heading level={2}>SS 304 Cold Rolled Coil</Heading><p>₹214.80 / kg <span className="positive">+₹2.63 today</span></p></div><div className="range-switch">{["1D", "7D", "1M", "3M", "1Y"].map((range, i) => <Button variant="ghost" className={i === 1 ? "is-active" : ""} key={range}>{range}</Button>)}</div></div>
        <div className="chart-area">
          <div className="chart-y"><span>₹218</span><span>₹214</span><span>₹210</span><span>₹206</span></div>
          <svg viewBox="0 0 900 250" preserveAspectRatio="none" aria-label="Seven-day rate chart"><defs><linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="var(--accent)" stopOpacity=".18"/><stop offset="100%" stopColor="var(--accent)" stopOpacity="0"/></linearGradient></defs><path className="area-fill" d="M0 220 C80 210 92 170 170 185 S280 140 350 155 S450 126 520 135 S620 80 680 98 S780 66 900 34 L900 250 L0 250Z"/><path className="area-line" d="M0 220 C80 210 92 170 170 185 S280 140 350 155 S450 126 520 135 S620 80 680 98 S780 66 900 34"/></svg>
          <div className="chart-x"><span>06 May</span><span>07 May</span><span>08 May</span><span>09 May</span><span>10 May</span><span>11 May</span><span>Today</span></div>
        </div>
        <div className="chart-stats">{[["7D high", "₹216.20"], ["7D low", "₹207.85"], ["Average", "₹211.64"], ["Volatility", "Low"], ["Trades indexed", "1,284"]].map(([a,b]) => <span key={a}><small>{a}</small><strong>{b}</strong></span>)}</div>
      </section>
      <section className="section-block"><div className="section-title"><div><small>WATCHLIST</small><Heading level={2}>Tracked benchmarks</Heading></div><Button variant="secondary"><Plus size={16} /> Add material</Button></div><MarketTable /></section>
    </div>
  );
}
