import { ChevronRight, Search } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { paths } from "../../app/paths";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Badge, Button, Input } from "../../components/ui";
import { readSession } from "../../lib/api/auth";
import { getDashboard, type BuyerDashboard, type DashboardActivity } from "../../lib/api/dashboard";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatDateTime, formatMoney, formatSignedMoney, titleCase } from "../../lib/pricingFormat";

const EMPTY: BuyerDashboard = {
  activeOrders: 0, openNegotiations: 0, openRequests: 0, pendingActions: 0, spendBasis: "material", spend: [],
  spendByProduct: [], spendBySupplier: [], variance: [],
  delivery: { available: false, note: "", onTime: 0, delivered: 0, percent: null },
  suppliers: [], alerts: [], ordersByStatus: {}, recentOrders: [], recentNegotiations: [],
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
  if (status === "processing" || status === "countered" || status === "ready" || status === "dispatched" || status === "in_transit") return "warning"
  return "info"
}

export function DashboardWorkspace() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const dashboard = useApiQuery("buyer-dashboard", (signal) => getDashboard(signal));
  const data = dashboard.data ?? EMPTY;
  const hideSuppliers = readSession()?.user.hideSuppliers === true;
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
          ["MATERIAL SPEND", spendText(data.spend), "Non-cancelled order totals. Freight and GST are not included."],
          ["OPEN REQUESTS", String(data.openRequests).padStart(2, "0"), "Draft, sent, or in negotiation"],
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
      <section className="section-block data-section">
        <div className="section-title"><div><small>ALERTS</small><p>The same items as the notification bell.</p></div></div>
        {data.alerts.length === 0 ? <p className="request-note">Nothing needs your attention.</p> : data.alerts.map((alert) => (
          <p key={alert.id} className="request-note"><strong>{alert.title}</strong> · {alert.detail}</p>
        ))}
      </section>
      <section className="section-block data-section">
        <div className="section-title"><div><small>MATERIAL SPEND</small><p>{hideSuppliers ? "By product. Cancelled orders are excluded." : "By supplier and product. Cancelled orders are excluded."}</p></div></div>
        {!hideSuppliers && (data.spendBySupplier.length === 0 ? <p className="request-note">No material spend yet.</p> : (
          <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Supplier</th><th>Orders</th><th>Material total</th></tr></thead><tbody>
            {data.spendBySupplier.map((row) => <tr key={`${row.label}:${row.currency}`}><td>{row.label}</td><td>{row.orderCount}</td><td>{formatMoney({ amount: row.amount, currency: row.currency }, 2)}</td></tr>)}
          </tbody></table></div>
        ))}
        {hideSuppliers && data.spendByProduct.length === 0 && <p className="request-note">No material spend yet.</p>}
        {data.spendByProduct.length > 0 && (
          <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Product</th><th>Orders</th><th>Material total</th></tr></thead><tbody>
            {data.spendByProduct.map((row) => <tr key={`${row.label}:${row.currency}`}><td>{row.label}</td><td>{row.orderCount}</td><td>{formatMoney({ amount: row.amount, currency: row.currency }, 2)}</td></tr>)}
          </tbody></table></div>
        )}
      </section>
      <section className="section-block data-section">
        <div className="section-title"><div><small>PRICE VARIANCE</small><p>Agreed unit price minus the snapshot frozen when the negotiation started.</p></div></div>
        {data.variance.length === 0 ? <p className="request-note">No order has a frozen snapshot, so variance is not shown.</p> : (
          <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Order</th><th>Agreed</th><th>Snapshot</th><th>Unit difference</th><th>Material difference</th></tr></thead><tbody>
            {data.variance.map((row) => (
              <tr key={row.orderId}>
                <td><strong>{row.orderNumber}</strong><small>{row.productName}</small></td>
                <td>{formatMoney(row.agreedUnitPrice, 4)}</td>
                <td>{formatMoney(row.snapshot, 4)}</td>
                <td>{formatSignedMoney(row.unitDifference)}</td>
                <td>{formatSignedMoney(row.materialDifference)}</td>
              </tr>
            ))}
          </tbody></table></div>
        )}
      </section>
      <section className="section-block data-section">
        <div className="section-title"><div><small>DELIVERY</small><p>{data.delivery.note || "On-time delivery uses a required date stored on the negotiation."}</p></div></div>
        {data.delivery.available ? <p className="request-note">{data.delivery.onTime} of {data.delivery.delivered} delivered on time · {data.delivery.percent}%</p> : null}
      </section>
      {!hideSuppliers && <section className="section-block data-section">
        <div className="section-title"><div><small>SUPPLIERS</small><p>Rates use only your negotiations and orders with that supplier.</p></div></div>
        {data.suppliers.length === 0 ? <p className="request-note">No suppliers in your negotiations or orders yet.</p> : (
          <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Supplier</th><th>Acceptance</th><th>Order cancellation</th><th>Quality</th><th>Response</th></tr></thead><tbody>
            {data.suppliers.map((row) => (
              <tr key={row.organisationId}>
                <td>{row.organisation}</td>
                <td>{row.acceptance.available ? `${row.acceptance.percent}%` : "Not calculated yet"}</td>
                <td>{row.orderCancellation.available ? `${row.orderCancellation.percent}%` : "Not calculated yet"}</td>
                <td>{row.quality.available ? `${row.quality.percent}%` : "Not calculated yet"}</td>
                <td>{row.responseTime.available ? `${row.responseTime.averageHours} h` : "Not calculated yet"}</td>
              </tr>
            ))}
          </tbody></table></div>
        )}
      </section>}
    </>
  );
}
