import { ChevronRight, Search } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { paths } from "../../app/paths";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Badge, Button, Input } from "../../components/ui";
import { getDashboard, type BuyerDashboard, type DashboardActivity } from "../../lib/api/dashboard";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatDateTime, formatMoney, titleCase } from "../../lib/pricingFormat";

const EMPTY: BuyerDashboard = {
  activeOrders: 0, openNegotiations: 0, pendingActions: 0, spend: [], ordersByStatus: {},
  recentOrders: [], recentNegotiations: [],
};

function spendText(spend: BuyerDashboard["spend"]) {
  if (!spend.length) return "—"
  return spend.map((row) => formatMoney({ amount: row.amount, currency: row.currency }, 2)).join(" · ")
}

function statusNote(counts: Record<string, number>) {
  const parts = Object.entries(counts).filter(([, count]) => count > 0).map(([status, count]) => `${count} ${titleCase(status)}`)
  return parts.length ? parts.join(" · ") : "No orders yet"
}

function tone(status: string): "neutral" | "positive" | "warning" | "negative" | "info" {
  if (status === "delivered" || status === "accepted") return "positive"
  if (status === "cancelled" || status === "rejected") return "negative"
  if (status === "processing" || status === "countered" || status === "ready" || status === "dispatched") return "warning"
  return "info"
}

export function DashboardWorkspace() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const dashboard = useApiQuery("buyer-dashboard", (signal) => getDashboard(signal));
  const data = dashboard.data ?? EMPTY;
  const activity = [...data.recentOrders, ...data.recentNegotiations].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  const term = search.trim().toLowerCase();
  const rows = activity.filter((row) => [row.reference, row.productName, row.counterparty, row.status].join(" ").toLowerCase().includes(term));
  const unavailable = { "aria-disabled": "true" as const, title: "Not available yet" };
  const open = (row: DashboardActivity) => {
    if (row.canReorder) navigate(`${paths.reorder}?order=${encodeURIComponent(row.id)}`);
    else if (row.kind === "order") navigate(`${paths.orders}?id=${encodeURIComponent(row.id)}`);
    else navigate(`${paths.negotiations}?id=${encodeURIComponent(row.id)}`);
  };
  return (
    <>
      <div className="metric-row">
        {[
          ["ACTIVE ORDERS", String(data.activeOrders).padStart(2, "0"), statusNote(data.ordersByStatus)],
          ["OPEN NEGOTIATIONS", String(data.openNegotiations).padStart(2, "0"), "Draft, open or countered"],
          ["PENDING ACTIONS", String(data.pendingActions).padStart(2, "0"), "Your turn to respond"],
          ["TOTAL SPEND", spendText(data.spend), "Agreed order prices"],
        ].map(([label, value, note]) => <div key={label}><small>{label}</small><strong>{value}</strong><span>{note}</span></div>)}
      </div>
      <section className="section-block data-section">
        <div className="data-toolbar"><label className="search-box search-box--small"><Search size={17}/><Input placeholder="Search dashboard…" value={search} onChange={(event) => setSearch(event.target.value)}/></label><div><Button variant="secondary" {...unavailable}>Filter</Button><Button variant="secondary" {...unavailable}>Export</Button></div></div>
        <AsyncContent isLoading={dashboard.isLoading && !dashboard.data} error={dashboard.error} onRetry={dashboard.reload} isEmpty={Boolean(dashboard.data) && activity.length === 0} emptyTitle="No activity yet" emptyMessage="Orders and negotiations will appear here." loadingLabel="Loading dashboard…">
          <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Reference</th><th>Material / description</th><th>Quantity</th><th>Value / rate</th><th>Status</th><th>Updated</th><th/></tr></thead><tbody>{rows.map((row) => (
            <tr key={`${row.kind}:${row.id}`} onClick={() => open(row)} style={{ cursor: "pointer" }}>
              <td><strong>{row.reference}</strong><small>{row.kind === "order" ? "Order" : "Negotiation"} · {row.counterparty}</small></td>
              <td><strong>{row.productName}</strong><small>{row.valueKind === "order_total" ? "Agreed order value" : "Current offer"}</small></td>
              <td>{Number(row.quantity).toLocaleString("en-IN")} {row.uom.toLowerCase()}</td>
              <td><strong>{row.value ? formatMoney(row.value, row.valueKind === "order_total" ? 2 : 4) : "—"}</strong></td>
              <td><Badge tone={tone(row.status)}>{titleCase(row.status)}</Badge></td>
              <td><small>{formatDateTime(row.updatedAt)}</small></td>
              <td>{row.canReorder ? <Button variant="secondary" onClick={(event) => { event.stopPropagation(); navigate(`${paths.reorder}?order=${encodeURIComponent(row.id)}`); }}>Reorder</Button> : <ChevronRight size={16}/>}</td>
            </tr>
          ))}</tbody></table></div>
        </AsyncContent>
      </section>
    </>
  );
}
