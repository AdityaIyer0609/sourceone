import { useState } from "react";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Button, Input } from "../../components/ui";
import { ApiError, getErrorMessage } from "../../lib/api/client";
import { listOwnListings, updateListing, type ListingAvailability, type SupplierListing } from "../../lib/api/listings";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatMoney, titleCase } from "../../lib/pricingFormat";

const AVAILABILITY: ListingAvailability[] = ["in_stock", "limited", "on_request"];

function ListingRow({ listing, onSaved }: { listing: SupplierListing; onSaved: () => void }) {
  const [price, setPrice] = useState(listing.askingPrice.amount);
  const [minimum, setMinimum] = useState(listing.minimumQuantity);
  const [availability, setAvailability] = useState<ListingAvailability>(listing.availability);
  const [active, setActive] = useState(listing.isActive);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await updateListing(listing.id, { askingPrice: price, minimumQuantity: minimum, availability, isActive: active });
      onSaved();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };
  return (
    <tr>
      <td><strong>{listing.productName}</strong><small>{listing.productCode} · {listing.originLabel || listing.originPin || "No origin saved"}</small></td>
      <td><Input aria-label={`Asking price for ${listing.productCode}`} value={price} onChange={(event) => setPrice(event.target.value)} /></td>
      <td><Input aria-label={`Minimum quantity for ${listing.productCode}`} value={minimum} onChange={(event) => setMinimum(event.target.value)} /></td>
      <td>
        <select className="input" aria-label={`Availability for ${listing.productCode}`} value={availability} onChange={(event) => setAvailability(event.target.value as ListingAvailability)}>
          {AVAILABILITY.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}
        </select>
      </td>
      <td>{formatMoney(listing.askingPrice, 4)} / {listing.uom.toLowerCase()}</td>
      <td><Button variant="ghost" onClick={() => setActive((value) => !value)}>{active ? "Active" : "Inactive"}</Button></td>
      <td>
        <Button disabled={busy} onClick={() => void save()}>Save</Button>
        {error ? <small className="negative">{getErrorMessage(error)}{error instanceof ApiError && error.code ? ` (${error.code})` : ""}</small> : null}
      </td>
    </tr>
  );
}

export function ListingsWorkspace() {
  const listings = useApiQuery("own-listings", (signal) => listOwnListings(signal));
  const rows = listings.data ?? [];
  return (
    <section className="section-block data-section">
      <AsyncContent isLoading={listings.isLoading && !listings.data} error={listings.error} onRetry={listings.reload} isEmpty={Boolean(listings.data) && rows.length === 0} emptyTitle="No listings yet" emptyMessage="A listing is your asking price for one product. Nothing is shown here until you create one." loadingLabel="Loading listings…">
        <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Product</th><th>Asking price</th><th>Minimum</th><th>Availability</th><th>Current</th><th>Shown</th><th/></tr></thead><tbody>
          {rows.map((listing) => <ListingRow key={`${listing.id}:${listing.askingPrice.amount}:${listing.isActive}`} listing={listing} onSaved={listings.reload} />)}
        </tbody></table></div>
      </AsyncContent>
    </section>
  );
}
