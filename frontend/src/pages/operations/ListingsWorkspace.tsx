import { Search } from "lucide-react";
import { useState } from "react";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Button, Input } from "../../components/ui";
import { ApiError, getErrorMessage } from "../../lib/api/client";
import { createListing, listOwnListings, updateListing, type ListingAvailability, type SupplierListing } from "../../lib/api/listings";
import { listProducts, type Product } from "../../lib/api/products";
import { SupplierSubmissionForm } from "./ProductSubmissions";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatMoney, titleCase } from "../../lib/pricingFormat";

const AVAILABILITY: ListingAvailability[] = ["in_stock", "limited", "on_request"];

function ListingRow({ listing, onSaved }: { listing: SupplierListing; onSaved: () => void }) {
  const [price, setPrice] = useState(listing.askingPrice.amount);
  const [minimum, setMinimum] = useState(listing.minimumQuantity);
  const [maximum, setMaximum] = useState(listing.maximumQuantity ?? "");
  const [availability, setAvailability] = useState<ListingAvailability>(listing.availability);
  const [active, setActive] = useState(listing.isActive);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await updateListing(listing.id, {
        askingPrice: price,
        minimumQuantity: minimum,
        maximumQuantity: availability === "limited" ? maximum : null,
        availability,
        isActive: active,
      });
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
        {availability === "limited"
          ? <Input aria-label={`Available quantity for ${listing.productCode}`} value={maximum} onChange={(event) => setMaximum(event.target.value)} />
          : <small>—</small>}
      </td>
      <td>
        <select className="input" aria-label={`Availability for ${listing.productCode}`} value={availability} onChange={(event) => setAvailability(event.target.value as ListingAvailability)}>
          {AVAILABILITY.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}
        </select>
      </td>
      <td>{formatMoney(listing.askingPrice, 4)} / {listing.uom.toLowerCase()}</td>
      <td><Button variant="ghost" onClick={() => setActive((value) => !value)}>{active ? "Active" : "Inactive"}</Button></td>
      <td>
        <Button disabled={busy || (availability === "limited" && !(Number(maximum) >= Number(minimum) && Number(maximum) > 0))} onClick={() => void save()}>Save</Button>
        {error ? <small className="negative">{getErrorMessage(error)}{error instanceof ApiError && error.code ? ` (${error.code})` : ""}</small> : null}
      </td>
    </tr>
  );
}

function CatalogueOffer({ product, onListed }: { product: Product; onListed: () => void }) {
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [minimum, setMinimum] = useState("");
  const [maximum, setMaximum] = useState("");
  const [availability, setAvailability] = useState<ListingAvailability>("in_stock");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const specs = product.specifications.filter((field) => field.value && field.key !== "uom" && field.key !== "description" && field.key !== "producer");
  const list = async () => {
    setBusy(true);
    setError(null);
    try {
      await createListing({
        productCode: product.productCode,
        askingPrice: price,
        currency,
        minimumQuantity: minimum,
        maximumQuantity: availability === "limited" ? maximum : null,
        availability,
      });
      onListed();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <article className="submission-review">
      <div>
        <small>{product.category}</small>
        <strong>{product.name}</strong>
        <span>{product.productCode}{product.subcategory ? ` · ${product.subcategory}` : ""} · {product.uom.label}</span>
        {specs.length > 0 && (
          <dl className="submission-specs">
            {specs.map((field) => <div key={field.key}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}
          </dl>
        )}
        <span>These specifications stay with the catalogue product. If your grade, MFI, density, application, quality, or unit differs, submit a new product below.</span>
      </div>
      <div className="submission-decision">
        <label>Asking price<Input aria-label={`Asking price for ${product.productCode}`} value={price} onChange={(event) => setPrice(event.target.value)} /></label>
        <label>Currency
          <select className="field-select" aria-label={`Currency for ${product.productCode}`} value={currency} onChange={(event) => setCurrency(event.target.value)}>
            <option value="INR">INR</option>
            <option value="USD">USD</option>
          </select>
        </label>
        <label>Minimum quantity<Input aria-label={`Minimum quantity for ${product.productCode}`} value={minimum} onChange={(event) => setMinimum(event.target.value)} /></label>
        {availability === "limited" && (
          <label>Available up to<Input aria-label={`Available quantity for ${product.productCode}`} value={maximum} onChange={(event) => setMaximum(event.target.value)} /></label>
        )}
        <label>Availability
          <select className="field-select" aria-label={`Availability for ${product.productCode}`} value={availability} onChange={(event) => setAvailability(event.target.value as ListingAvailability)}>
            {AVAILABILITY.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}
          </select>
        </label>
        <div className="submission-decision__actions">
          <Button disabled={busy || !(Number(price) > 0) || !(Number(minimum) > 0) || (availability === "limited" && !(Number(maximum) >= Number(minimum) && Number(maximum) > 0))} onClick={() => void list()}>{busy ? "Saving…" : "List this product"}</Button>
        </div>
        {error ? <p className="negative">{error}</p> : null}
      </div>
    </article>
  );
}

export function ListingsWorkspace() {
  const listings = useApiQuery("own-listings", (signal) => listOwnListings(signal));
  const catalogue = useApiQuery("listings-catalogue", (signal) => listProducts({}, signal));
  const [search, setSearch] = useState("");
  const rows = listings.data ?? [];
  const listed = new Set(rows.map((row) => row.productCode));
  const term = search.trim().toLowerCase();
  const available = (catalogue.data ?? []).filter((product) => {
    if (listed.has(product.productCode)) return false;
    if (!term) return true;
    const haystack = [product.productCode, product.name, product.category, product.subcategory, product.description, ...product.specifications.map((field) => field.value)].join(" ").toLowerCase();
    return haystack.includes(term);
  });
  const refresh = () => {
    listings.reload();
    catalogue.reload();
  };
  return (
    <>
    <section className="section-block data-section" style={{ marginBottom: 16 }}>
      <div className="step-label" style={{ padding: "16px 18px 0" }}><span>01</span><div><strong>Your listings</strong><small>Saving a price updates this offer. It does not change the catalogue specifications or publish a benchmark.</small></div></div>
      <AsyncContent isLoading={listings.isLoading && !listings.data} error={listings.error} onRetry={listings.reload} isEmpty={Boolean(listings.data) && rows.length === 0} emptyTitle="No listings yet" emptyMessage="Choose a catalogue product below and set your asking price." loadingLabel="Loading listings…">
        <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Product</th><th>Asking price</th><th>Minimum</th><th>Available up to</th><th>Availability</th><th>Current</th><th>Shown</th><th/></tr></thead><tbody>
          {rows.map((listing) => <ListingRow key={`${listing.id}:${listing.askingPrice.amount}:${listing.isActive}`} listing={listing} onSaved={listings.reload} />)}
        </tbody></table></div>
      </AsyncContent>
    </section>
    <section className="section-block data-section submission-queue" style={{ marginBottom: 16 }}>
      <div className="step-label"><span>02</span><div><strong>Catalogue you can list</strong><small>These products are already in the catalogue and you do not list them yet. Your price, minimum, and availability are yours. The specifications are not.</small></div></div>
      <div className="data-toolbar">
        <label className="search-box search-box--small"><Search size={17}/><Input placeholder="Search catalogue…" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      </div>
      <AsyncContent isLoading={catalogue.isLoading && !catalogue.data} error={catalogue.error} onRetry={catalogue.reload} isEmpty={Boolean(catalogue.data) && available.length === 0} emptyTitle={term ? "No matching products" : "Nothing left to list"} emptyMessage={term ? "Try another name, code, or specification." : "You already have a listing for every active catalogue product. If you sell something that is not here, submit it below."} loadingLabel="Loading catalogue…">
        <div>{available.map((product) => <CatalogueOffer key={product.productCode} product={product} onListed={refresh} />)}</div>
      </AsyncContent>
    </section>
    <SupplierSubmissionForm />
    </>
  );
}
