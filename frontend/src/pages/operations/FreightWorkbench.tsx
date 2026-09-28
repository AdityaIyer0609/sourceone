import { ArrowRight, Truck } from "lucide-react";
import { Badge, Button, Input } from "../../components/ui";

export function FreightWorkbench() {
  return (
    <div className="freight-layout">
      <section className="workbench">
        <div className="step-label"><span>01</span><div><strong>Material & quantity</strong><small>What are you moving?</small></div></div>
        <div className="form-grid"><label>Item<Input defaultValue="SS 304 Cold Rolled Coil" /></label><label>Quantity<div className="input-combo"><Input defaultValue="12,000" /><span>KG</span></div></label></div>
        <div className="step-label"><span>02</span><div><strong>Route</strong><small>Supply point to delivery location</small></div></div>
        <div className="route-fields"><label>Dispatch PIN<Input defaultValue="400001" /></label><div className="route-line"><span/><Truck size={18}/><span/></div><label>Delivery PIN<Input defaultValue="390020" /></label></div>
        <div className="step-label"><span>03</span><div><strong>Commercial terms</strong><small>Tax and handling preferences</small></div></div>
        <div className="form-grid"><label>Delivery mode<Input defaultValue="Full truck load (FTL)" /></label><label>Insurance<Input defaultValue="Transit insurance included" /></label></div>
        <Button className="wide-button">Calculate best landed cost <ArrowRight size={17}/></Button>
      </section>
      <aside className="landed-summary"><small>ESTIMATED LANDED COST</small><strong>₹26,36,640</strong><p>₹219.72 / kg delivered</p><div className="cost-lines"><span><small>Material</small><strong>₹25,77,600</strong></span><span><small>Freight · 438 km</small><strong>₹51,000</strong></span><span><small>Handling & insurance</small><strong>₹8,040</strong></span></div><div className="route-option"><Truck size={20}/><div><strong>BlueDart Industrial</strong><small>FTL · 18 MT · 1–2 days</small></div><Badge tone="positive">BEST</Badge></div><Button variant="secondary" className="wide-button">Add to purchase request</Button></aside>
    </div>
  );
}
