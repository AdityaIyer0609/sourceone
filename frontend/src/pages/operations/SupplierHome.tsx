import { useNavigate } from "react-router-dom";
import { paths } from "../../app/paths";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Button } from "../../components/ui";
import { getSupplierDashboard, type SupplierDashboard } from "../../lib/api/dashboard";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatMoney, titleCase } from "../../lib/pricingFormat";

const EMPTY: SupplierDashboard = {
  openRequests: 0, openNegotiations: 0, ordersToConfirm: 0, listingsToReview: 0,
  requests: [], negotiations: [], orders: [], listings: [], documents: [], alerts: [],
  performance: {
    acceptance: { available: false, note: "", percent: null, averageHours: null, count: 0, total: 0 },
    orderCancellation: { available: false, note: "", percent: null, averageHours: null, count: 0, total: 0 },
    onTimeDelivery: { available: false, note: "", percent: null, averageHours: null, count: 0, total: 0 },
    quality: { available: false, note: "", percent: null, averageHours: null, count: 0, total: 0 },
    responseTime: { available: false, note: "", sampleCount: 0, averageHours: null },
  },
};

function rateText(row: { available: boolean; percent: string | null }) {
  return row.available && row.percent ? `${row.percent}%` : "—";
}

export function SupplierHome() {
  const navigate = useNavigate();
  const dashboard = useApiQuery("supplier-dashboard", (signal) => getSupplierDashboard(signal));
  const data = dashboard.data ?? EMPTY;
  const performance = data.performance;
  return (
    <>
      <div className="metric-row">
        {[
          ["RFQS AWAITING YOU", String(data.openRequests).padStart(2, "0"), "Sent requests where it is your turn"],
          ["YOUR TURN", String(data.openNegotiations).padStart(2, "0"), "Negotiations waiting on you"],
          ["ORDERS TO CONFIRM", String(data.ordersToConfirm).padStart(2, "0"), "Placed orders"],
          ["LISTINGS TO REVIEW", String(data.listingsToReview).padStart(2, "0"), "Inactive or on request"],
        ].map(([label, value, note]) => <div key={label}><small>{label}</small><strong>{value}</strong><span>{note}</span></div>)}
      </div>
      <AsyncContent isLoading={dashboard.isLoading && !dashboard.data} error={dashboard.error} onRetry={dashboard.reload} isEmpty={false} loadingLabel="Loading your work…">
        <div className="supplier-home">
          <section className="section-block data-section">
            <div className="section-title"><div><small>WAITING</small><p>The same items as the notification bell, plus requests sent to you.</p></div></div>
            {data.requests.length === 0 && data.negotiations.length === 0 && data.orders.length === 0 ? <p className="request-note">Nothing is waiting on you.</p> : (
              <div className="queue-list">
                {data.requests.map((row) => (
                  <div className="queue-row" key={row.id}>
                    <div><small>Request</small><strong>{row.title}</strong><span>{row.detail}</span></div>
                    <Button variant="secondary" onClick={() => navigate(paths.purchaseRequests)}>Open requests</Button>
                  </div>
                ))}
                {data.negotiations.map((row) => (
                  <div className="queue-row" key={row.id}>
                    <div><small>Negotiation</small><strong>{row.title}</strong><span>{row.detail}</span></div>
                    <Button variant="secondary" onClick={() => navigate(`${paths.negotiations}?id=${encodeURIComponent(row.id)}`)}>Open negotiation</Button>
                  </div>
                ))}
                {data.orders.map((row) => (
                  <div className="queue-row" key={row.id}>
                    <div><small>Order</small><strong>{row.title}</strong><span>{row.detail}</span></div>
                    <Button variant="secondary" onClick={() => navigate(`${paths.orders}?id=${encodeURIComponent(row.id)}`)}>Open order</Button>
                  </div>
                ))}
              </div>
            )}
          </section>
          <section className="section-block data-section">
            <div className="section-title"><div><small>LISTINGS</small><p>Inactive listings and listings marked on request.</p></div></div>
            {data.listings.length === 0 ? <p className="request-note">No listing needs review.</p> : (
              <div className="market-table-wrap"><table className="market-table market-table--fit"><colgroup><col /><col /><col /><col /></colgroup><thead><tr><th>Product</th><th>Asking price</th><th>Availability</th><th/></tr></thead><tbody>
                {data.listings.map((row) => (
                  <tr key={row.id}>
                    <td><strong>{row.productName}</strong><small>{row.productCode}</small></td>
                    <td>{formatMoney(row.askingPrice, 4)}</td>
                    <td>{row.isActive ? titleCase(row.availability) : "Inactive"}</td>
                    <td><Button variant="secondary" onClick={() => navigate(paths.listings)}>Edit</Button></td>
                  </tr>
                ))}
              </tbody></table></div>
            )}
          </section>
          <section className="section-block data-section">
            <div className="section-title"><div><small>DOCUMENTS</small><p>Fulfilment files stored on your orders.</p></div></div>
            {data.documents.length === 0 ? <p className="request-note">No fulfilment documents are stored on your orders yet.</p> : (
              <div className="market-table-wrap"><table className="market-table market-table--fit"><colgroup><col /><col /><col /><col /></colgroup><thead><tr><th>Order</th><th>File</th><th>Status</th><th/></tr></thead><tbody>
                {data.documents.map((row) => (
                  <tr key={row.id}>
                    <td>{row.orderNumber}</td>
                    <td><strong>{row.filename}</strong><small>{titleCase(row.documentType)}</small></td>
                    <td>{titleCase(row.status)}</td>
                    <td><Button variant="secondary" onClick={() => navigate(`${paths.orders}?id=${encodeURIComponent(row.orderId)}`)}>Open order</Button></td>
                  </tr>
                ))}
              </tbody></table></div>
            )}
          </section>
          <section className="section-block data-section">
            <div className="section-title"><div><small>PERFORMANCE</small><p>Calculated from this company's negotiations, orders, and fulfilment documents.</p></div></div>
            <div className="perf-grid">
              <div><small>ACCEPTANCE</small><strong>{rateText(performance.acceptance)}</strong><span>{performance.acceptance.note}</span></div>
              <div><small>ORDER CANCELLATION</small><strong>{rateText(performance.orderCancellation)}</strong><span>{performance.orderCancellation.note}</span></div>
              <div><small>QUALITY</small><strong>{rateText(performance.quality)}</strong><span>{performance.quality.note}</span></div>
              <div><small>RESPONSE</small><strong>{performance.responseTime.available && performance.responseTime.averageHours ? `${performance.responseTime.averageHours} h` : "—"}</strong><span>{performance.responseTime.note}</span></div>
              <div><small>ON TIME</small><strong>{rateText(performance.onTimeDelivery)}</strong><span>{performance.onTimeDelivery.note}</span></div>
            </div>
          </section>
        </div>
      </AsyncContent>
    </>
  );
}
