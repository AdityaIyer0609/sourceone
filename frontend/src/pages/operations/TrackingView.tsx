import { Check, Truck } from "lucide-react";
import { Badge, Heading } from "../../components/ui";
import { shipmentTimeline } from "../../mocks/data";

export function TrackingView() {
  return (
    <div className="tracking-layout">
      <section className="tracking-map"><div className="map-grid"/><div className="route-path"><i className="origin"/><span/><Truck size={24}/><span/><i className="destination"/></div><div className="map-location map-location--a"><strong>Mumbai warehouse</strong><small>Dispatched · 08:10</small></div><div className="map-location map-location--b"><strong>Ardent Plant 02</strong><small>ETA today · 17:30</small></div></section>
      <aside className="shipment-panel"><Badge tone="info">IN TRANSIT</Badge><Heading level={2}>SO-4857</Heading><p>SS 304 CR Coil · 12,000 kg</p><div className="eta-block"><small>ESTIMATED ARRIVAL</small><strong>Today, 5:30 PM</strong><span>On schedule</span></div><div className="timeline">{shipmentTimeline.map(([a,b],i)=><div className={i<4?"done":""} key={a}><i>{i<3?<Check size={12}/>:null}</i><span><strong>{a}</strong><small>{b}</small></span></div>)}</div></aside>
    </div>
  );
}
