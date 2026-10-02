import { useState } from "react";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Button } from "../../components/ui";
import { getErrorMessage } from "../../lib/api/client";
import { listSupplierMatches, type SupplierMatch } from "../../lib/api/listings";
import { assignOrder, listUnassignedOrders, type UnassignedOrder } from "../../lib/api/orders";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatDateTime, formatMoney } from "../../lib/pricingFormat";

export function AssignOrdersWorkspace() {
  const orders = useApiQuery("unassigned-orders", (signal) => listUnassignedOrders(signal));
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selected = orders.data?.find((order) => order.id === picked) ?? orders.data?.[0] ?? null;
  const matches = useApiQuery(
    selected?.destinationPin ? `assign-matches:${selected.id}:${selected.destinationPin}` : null,
    (signal) => listSupplierMatches(selected!.productCode, {
      quantity: selected!.quantity,
      uom: selected!.uom,
      destinationPin: selected!.destinationPin!,
      currency: selected!.currency,
    }, signal),
  );
  const assign = async (order: UnassignedOrder, supplier: SupplierMatch) => {
    setBusy(supplier.supplierUserId);
    setError(null);
    try {
      await assignOrder(order.id, supplier.supplierUserId);
      setPicked(null);
      orders.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusy(null);
    }
  };
  return (
    <AsyncContent isLoading={orders.isLoading && !orders.data} error={orders.error} onRetry={orders.reload} isEmpty={!orders.data?.length} emptyTitle="No orders waiting" emptyMessage="Customer orders appear here until a supplier is chosen." loadingLabel="Loading orders…">
      <div className="supplier-home">
        <section className="section-block data-section">
          <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Order</th><th>Product</th><th>Customer</th><th>Quantity</th><th>Price</th><th>PIN</th><th>Placed</th></tr></thead><tbody>
            {(orders.data ?? []).map((order) => (
              <tr key={order.id} onClick={() => setPicked(order.id)}>
                <td><strong>{order.orderNumber}</strong></td>
                <td>{order.productName}<small>{order.productCode}</small></td>
                <td>{order.buyerOrganisation}</td>
                <td>{Number(order.quantity).toLocaleString("en-IN")} {order.uom.toLowerCase()}</td>
                <td>{formatMoney({ amount: order.unitPrice, currency: order.currency }, 4)}</td>
                <td>{order.destinationPin ?? "—"}</td>
                <td><small>{formatDateTime(order.createdAt)}</small></td>
              </tr>
            ))}
          </tbody></table></div>
        </section>
        {selected && (
          <section className="section-block data-section">
            <div className="section-title"><div><small>CHOOSE A SUPPLIER</small><p>{selected.orderNumber} · {selected.productName}. The customer’s price stays {formatMoney({ amount: selected.unitPrice, currency: selected.currency }, 4)}.</p></div></div>
            {error && <p className="negative">{error}</p>}
            <AsyncContent isLoading={matches.isLoading && !matches.data} error={matches.error} onRetry={matches.reload} isEmpty={!matches.data?.matches.length} emptyTitle="No supplier can take this" emptyMessage="A listing needs enough stock, and a delivery PIN is required to estimate freight." loadingLabel="Loading suppliers…">
              <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Supplier</th><th>Asking price</th><th>Stock</th><th>Freight</th><th/></tr></thead><tbody>
                {matches.data?.matches.map((match) => (
                  <tr key={match.supplierUserId}>
                    <td><strong>{match.organisation}</strong><small>{match.supplierName}</small></td>
                    <td>{match.askingPrice ? formatMoney(match.askingPrice, 4) : "—"}</td>
                    <td>{match.soldOut ? "Sold out" : match.availability === "on_request" ? "On request" : match.maximumQuantity ? `${Number(match.maximumQuantity).toLocaleString("en-IN")} ${selected.uom.toLowerCase()}` : "In stock"}</td>
                    <td>{match.freightStatus === "estimated" && match.freight ? formatMoney(match.freight) : "On request"}</td>
                    <td><Button disabled={busy !== null || match.soldOut} onClick={() => void assign(selected, match)}>{busy === match.supplierUserId ? "Assigning…" : "Assign"}</Button></td>
                  </tr>
                ))}
              </tbody></table></div>
            </AsyncContent>
          </section>
        )}
      </div>
    </AsyncContent>
  );
}
