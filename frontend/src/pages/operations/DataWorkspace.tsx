import { ChevronRight, Filter, Search } from "lucide-react";
import { Badge, Button, Input } from "../../components/ui";
import { workspaceRows } from "../../mocks/data";

export function DataWorkspace({ screen }: { screen: string }) {
  const isAdmin = screen === "Item Master" || screen === "Rate Management";
  return (
    <>
      <div className="metric-row">
        {[
          ["OPEN", isAdmin ? "142" : "18", "+4 this week"],
          ["IN PROGRESS", isAdmin ? "36" : "07", "Within SLA"],
          ["COMPLETED", isAdmin ? "4,684" : "126", "Last 90 days"],
          ["VALUE / IMPACT", isAdmin ? "98.6%" : "₹42.8L", isAdmin ? "Data quality" : "Active value"],
        ].map(([a,b,c]) => <div key={a}><small>{a}</small><strong>{b}</strong><span>{c}</span></div>)}
      </div>
      <section className="section-block data-section">
        <div className="data-toolbar"><label className="search-box search-box--small"><Search size={17}/><Input placeholder={`Search ${screen.toLowerCase()}…`}/></label><div><Button variant="secondary"><Filter size={16}/> Filter</Button><Button variant="secondary">Export</Button></div></div>
        <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Reference</th><th>Material / description</th><th>Quantity</th><th>Value / rate</th><th>Status</th><th>Updated</th><th/></tr></thead><tbody>{workspaceRows.map((row,i)=><tr key={row[0]}><td><strong>{row[0]}</strong></td><td><strong>{row[1]}</strong><small>Verified specification</small></td><td>{row[2]}</td><td><strong>{row[3]}</strong></td><td><Badge tone={i===2?"warning":i===4?"positive":"info"}>{row[4]}</Badge></td><td><small>{row[5]}</small></td><td><ChevronRight size={16}/></td></tr>)}</tbody></table></div>
      </section>
    </>
  );
}
