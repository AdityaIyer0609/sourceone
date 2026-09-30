import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { paths } from "../app/paths";
import { AsyncContent } from "../components/feedback/AsyncContent";
import { Badge, Button, Heading, Input } from "../components/ui";
import { getErrorMessage } from "../lib/api/client";
import { getSupplierProfile, saveServiceRegions, saveVerification, type CountRate, type SupplierProfile } from "../lib/api/suppliers";
import { useApiQuery } from "../lib/api/useApiQuery";
import { formatDateTime, formatMoney, titleCase } from "../lib/pricingFormat";

function rateValue(rate: CountRate) {
  return rate.available && rate.percent ? `${rate.percent}%` : "—";
}

function responseValue(profile: SupplierProfile) {
  return profile.responseTime.available && profile.responseTime.averageHours ? `${profile.responseTime.averageHours} h` : "—";
}

export function SupplierProfilePage() {
  const { organisationId = "" } = useParams();
  const profile = useApiQuery(organisationId ? `supplier:${organisationId}` : null, (signal) => getSupplierProfile(organisationId, signal));
  const data = profile.data;
  const [regions, setRegions] = useState<{ label: string; pinPrefix: string }[] | null>(null);
  const [label, setLabel] = useState("");
  const [prefix, setPrefix] = useState("");
  const [status, setStatus] = useState<SupplierProfile["verificationStatus"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const draftRegions = regions ?? (data?.serviceRegions.map((region) => ({ label: region.label, pinPrefix: region.pinPrefix ?? "" })) ?? []);
  const draftStatus = status ?? data?.verificationStatus ?? "unverified";

  const saveRegions = async () => {
    setBusy(true);
    setError(null);
    try {
      await saveServiceRegions(organisationId, draftRegions.map((region) => ({ label: region.label, pinPrefix: region.pinPrefix || null })));
      setRegions(null);
      profile.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const saveStatus = async () => {
    setBusy(true);
    setError(null);
    try {
      await saveVerification(organisationId, draftStatus);
      setStatus(null);
      profile.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <AsyncContent isLoading={profile.isLoading && !data} error={profile.error} onRetry={profile.reload} isEmpty={false} loadingLabel="Loading supplier…">
        {data && (
          <>
            <div className="page-heading">
              <div>
                <small>SUPPLIER</small>
                <Heading level={1}>{data.name}</Heading>
                <p>{data.dispatchLabel ? `${data.dispatchLabel} · ` : ""}{data.dispatchPin ? `Dispatch PIN ${data.dispatchPin}` : "No dispatch PIN yet"}</p>
              </div>
              <Badge tone={data.verificationStatus === "verified" ? "positive" : data.verificationStatus === "pending" ? "warning" : "neutral"}>{titleCase(data.verificationStatus)}</Badge>
            </div>
            <div className="metric-row">
              <div><small>RESPONSE TIME</small><strong>{responseValue(data)}</strong><span>{data.responseTime.note}</span></div>
              <div><small>ACCEPTANCE</small><strong>{rateValue(data.acceptance)}</strong><span>{data.acceptance.available ? `${data.acceptance.count} of ${data.acceptance.total} decided` : data.acceptance.note}</span></div>
              <div><small>ORDER CANCELLATION</small><strong>{rateValue(data.orderCancellation)}</strong><span>{data.orderCancellation.available ? `${data.orderCancellation.count} of ${data.orderCancellation.total} orders` : data.orderCancellation.note}</span></div>
              <div><small>ON-TIME DELIVERY</small><strong>—</strong><span>{data.onTimeDelivery.note}</span></div>
            </div>
            <p className="request-note">{data.quality.note} Quotes {data.quoteCount}. Orders {data.orderCount}. These counts are stored negotiations and orders, not a score.</p>
            {error && <p className="negative">{error}</p>}
            <section className="section-block" style={{ marginBottom: 16, padding: 16 }}>
              <Heading level={2}>Service regions</Heading>
              <p>{data.serviceRegions.length ? data.serviceRegions.map((region) => region.pinPrefix ? `${region.label} (${region.pinPrefix})` : region.label).join(" · ") : "This supplier has not declared any service regions."}</p>
              <p>Dispatch PIN {data.dispatchPin ?? "is not set"}. Regions do not replace it, and freight is still estimated from saved lanes.</p>
              {data.canEditRegions && (
                <>
                  <div className="form-grid" style={{ marginTop: 12 }}>
                    {draftRegions.map((region, index) => (
                      <label key={`${region.label}-${index}`}>{region.label}
                        <Button variant="ghost" onClick={() => setRegions(draftRegions.filter((_, item) => item !== index))}>Remove</Button>
                      </label>
                    ))}
                    <label>Region<Input aria-label="Region name" value={label} onChange={(event) => setLabel(event.target.value)} /></label>
                    <label>PIN prefix<Input aria-label="PIN prefix" value={prefix} onChange={(event) => setPrefix(event.target.value)} placeholder="First 3 digits" /></label>
                  </div>
                  <div className="modal-actions">
                    <Button variant="secondary" disabled={!label.trim()} onClick={() => { setRegions([...draftRegions, { label: label.trim(), pinPrefix: prefix.trim() }]); setLabel(""); setPrefix(""); }}>Add region</Button>
                    <Button disabled={busy} onClick={() => void saveRegions()}>{busy ? "Saving…" : "Save regions"}</Button>
                  </div>
                </>
              )}
              {data.canSetVerification && (
                <div className="modal-actions">
                  <label>Verification
                    <select className="field-select" aria-label="Verification" value={draftStatus} onChange={(event) => setStatus(event.target.value as SupplierProfile["verificationStatus"])}>
                      <option value="unverified">Unverified</option>
                      <option value="pending">Pending</option>
                      <option value="verified">Verified</option>
                    </select>
                  </label>
                  <Button disabled={busy} onClick={() => void saveStatus()}>Save verification</Button>
                </div>
              )}
            </section>
            <section className="section-block data-section" style={{ marginBottom: 16 }}>
              <div className="data-toolbar"><strong>Products</strong></div>
              {data.products.length === 0 ? <p className="request-note">No active listings.</p> : (
                <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Material</th><th>Asking price</th><th>Minimum</th><th>Availability</th></tr></thead><tbody>
                  {data.products.map((item) => (
                    <tr key={item.productCode}>
                      <td><Link className="org-link" to={paths.productDetail(item.productCode)}><strong>{item.name}</strong></Link><small>{item.productCode}</small></td>
                      <td>{formatMoney(item.askingPrice)}</td>
                      <td>{Number(item.minimumQuantity).toLocaleString("en-IN")} {item.uom.toLowerCase()}</td>
                      <td>{titleCase(item.availability)}</td>
                    </tr>
                  ))}
                </tbody></table></div>
              )}
            </section>
            <section className="section-block data-section" style={{ marginBottom: 16 }}>
              <div className="data-toolbar"><strong>People</strong></div>
              {data.people.length === 0 ? <p className="request-note">No active users.</p> : (
                <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Name</th><th>Email</th></tr></thead><tbody>
                  {data.people.map((person) => <tr key={person.name}><td>{person.name}</td><td>{person.email ?? "—"}</td></tr>)}
                </tbody></table></div>
              )}
            </section>
            <section className="section-block data-section" style={{ marginBottom: 16 }}>
              <div className="data-toolbar"><strong>Quotes</strong></div>
              {data.quotes.length === 0 ? <p className="request-note">No negotiations yet.</p> : (
                <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Negotiation</th><th>Material</th><th>Latest offer</th><th>Status</th><th>Updated</th></tr></thead><tbody>
                  {data.quotes.map((quote) => (
                    <tr key={quote.id}>
                      <td><Link className="org-link" to={`${paths.negotiations}?id=${encodeURIComponent(quote.id)}`}>{quote.reference}</Link></td>
                      <td>{quote.productName}</td>
                      <td>{quote.latestOffer ? formatMoney(quote.latestOffer) : "—"}</td>
                      <td>{titleCase(quote.status)}</td>
                      <td><small>{formatDateTime(quote.updatedAt)}</small></td>
                    </tr>
                  ))}
                </tbody></table></div>
              )}
            </section>
            <section className="section-block data-section">
              <div className="data-toolbar"><strong>Orders</strong></div>
              {data.orders.length === 0 ? <p className="request-note">No orders yet.</p> : (
                <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Order</th><th>Material</th><th>Material value</th><th>Status</th><th>Updated</th></tr></thead><tbody>
                  {data.orders.map((order) => (
                    <tr key={order.id}>
                      <td><Link className="org-link" to={`${paths.orders}?id=${encodeURIComponent(order.id)}`}>{order.reference}</Link></td>
                      <td>{order.productName}</td>
                      <td>{formatMoney(order.totalValue, 2)}</td>
                      <td>{titleCase(order.status)}</td>
                      <td><small>{formatDateTime(order.updatedAt)}</small></td>
                    </tr>
                  ))}
                </tbody></table></div>
              )}
            </section>
          </>
        )}
      </AsyncContent>
    </div>
  );
}
