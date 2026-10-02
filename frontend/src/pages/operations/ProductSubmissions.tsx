import { useState } from "react";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Badge, Button, Input } from "../../components/ui";
import { getErrorMessage } from "../../lib/api/client";
import type { ListingAvailability } from "../../lib/api/listings";
import {
  SPEC_FIELDS, acceptSubmission, listAdminSubmissions, listOwnSubmissions, rejectSubmission, submitProduct,
  type ProductSubmission,
} from "../../lib/api/submissions";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatMoney, titleCase } from "../../lib/pricingFormat";

const AVAILABILITY: ListingAvailability[] = ["in_stock", "limited", "on_request"];
const EMPTY_SPECS = Object.fromEntries(SPEC_FIELDS.map(([key]) => [key, ""]));
const EMPTY = {
  proposedCode: "", name: "", category: "", subcategory: "", description: "",
  askingPrice: "", currency: "INR", minimumQuantity: "", maximumQuantity: "", availability: "in_stock" as ListingAvailability,
  specifications: { ...EMPTY_SPECS },
};

export function SupplierSubmissionForm() {
  const submissions = useApiQuery("own-submissions", (signal) => listOwnSubmissions(signal));
  const [draft, setDraft] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ready = Boolean(
    draft.proposedCode.trim() && draft.name.trim() && draft.category.trim()
    && Number(draft.askingPrice) > 0 && Number(draft.minimumQuantity) > 0
    && (draft.availability === "on_request" || (Number(draft.maximumQuantity) >= Number(draft.minimumQuantity) && Number(draft.maximumQuantity) > 0))
    && SPEC_FIELDS.every(([key]) => draft.specifications[key]?.trim()),
  );
  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      await submitProduct({
        proposedCode: draft.proposedCode.trim(),
        name: draft.name.trim(),
        category: draft.category.trim(),
        subcategory: draft.subcategory.trim() || null,
        description: draft.description.trim() || null,
        uom: "KG",
        specifications: draft.specifications,
        askingPrice: draft.askingPrice,
        currency: draft.currency,
        minimumQuantity: draft.minimumQuantity,
        maximumQuantity: draft.availability === "on_request" ? null : draft.maximumQuantity,
        availability: draft.availability,
      });
      setDraft({ ...EMPTY, specifications: { ...EMPTY_SPECS } });
      submissions.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const rows = submissions.data ?? [];
  return (
    <section className="section-block" style={{ marginBottom: 16, padding: 16 }}>
      <div className="step-label"><span>03</span><div><strong>Submit a product</strong><small>Use this when no catalogue product matches your grade, MFI, density, application, quality, or unit. A pricing admin reviews it before it appears in the marketplace. If it is accepted, your asking price is listed on that product.</small></div></div>
      <div className="form-grid">
        <label>Product code<Input aria-label="Proposed product code" value={draft.proposedCode} onChange={(event) => setDraft({ ...draft, proposedCode: event.target.value })} /></label>
        <label>Name<Input aria-label="Product name" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
        <label>Category<Input aria-label="Category" value={draft.category} onChange={(event) => setDraft({ ...draft, category: event.target.value })} /></label>
        <label>Subcategory<Input aria-label="Subcategory" value={draft.subcategory} onChange={(event) => setDraft({ ...draft, subcategory: event.target.value })} /></label>
        <label className="form-grid__wide">Description<Input aria-label="Description" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
        <label>UOM<Input aria-label="UOM" value="KG" disabled /></label>
        {SPEC_FIELDS.map(([key, label]) => (
          <label key={key}>{label}<Input aria-label={label} required value={draft.specifications[key] ?? ""} onChange={(event) => setDraft({ ...draft, specifications: { ...draft.specifications, [key]: event.target.value } })} /></label>
        ))}
        <label>Asking price<Input aria-label="Asking price" value={draft.askingPrice} onChange={(event) => setDraft({ ...draft, askingPrice: event.target.value })} /></label>
        <label>Currency
          <select className="input" aria-label="Currency" value={draft.currency} onChange={(event) => setDraft({ ...draft, currency: event.target.value })}>
            <option value="INR">INR</option>
            <option value="USD">USD</option>
          </select>
        </label>
        <label>Minimum quantity<Input aria-label="Minimum quantity" value={draft.minimumQuantity} onChange={(event) => setDraft({ ...draft, minimumQuantity: event.target.value })} /></label>
        {draft.availability !== "on_request" && (
          <label>Available quantity<Input aria-label="Available quantity" value={draft.maximumQuantity} onChange={(event) => setDraft({ ...draft, maximumQuantity: event.target.value })} /></label>
        )}
        <label>Availability
          <select className="input" aria-label="Availability" value={draft.availability} onChange={(event) => setDraft({ ...draft, availability: event.target.value as ListingAvailability })}>
            {AVAILABILITY.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}
          </select>
        </label>
      </div>
      {error && <p className="negative">{error}</p>}
      <div className="modal-actions">
        <Button disabled={busy || !ready} onClick={() => void send()}>{busy ? "Submitting…" : "Submit for review"}</Button>
      </div>
      {rows.length > 0 && (
        <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Code</th><th>Product</th><th>Specifications</th><th>Asking price</th><th>Status</th></tr></thead><tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td><strong>{row.proposedCode}</strong><small>{row.productCode ? `Catalogue ${row.productCode}` : "Not in the catalogue yet"}</small></td>
              <td><strong>{row.name}</strong><small>{row.category} · {row.uom}</small></td>
              <td><small>{SPEC_FIELDS.map(([key, label]) => `${label} ${row.specifications[key] ?? "—"}`).join(" · ")}</small></td>
              <td>{formatMoney(row.askingPrice, 4)}<small>Min {row.minimumQuantity}{row.maximumQuantity ? `–${row.maximumQuantity}` : ""} {row.uom}</small></td>
              <td>
                <Badge tone={row.status === "accepted" ? "positive" : row.status === "rejected" ? "negative" : "warning"}>{row.status.toUpperCase()}</Badge>
                {row.reviewNote ? <small>{row.reviewNote}</small> : null}
              </td>
            </tr>
          ))}
        </tbody></table></div>
      )}
    </section>
  );
}

function ReviewRow({ row, onDone }: { row: ProductSubmission; onDone: () => void }) {
  const [code, setCode] = useState(row.proposedCode);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const decide = async (accept: boolean) => {
    setBusy(true);
    setError(null);
    try {
      if (accept) await acceptSubmission(row.id, code.trim() || row.proposedCode);
      else await rejectSubmission(row.id, note.trim());
      onDone();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <article className="submission-review">
      <div>
        <small>{row.organisation}</small>
        <strong>{row.name}</strong>
        <span>{row.supplierName} · {row.category}{row.subcategory ? ` · ${row.subcategory}` : ""} · {row.uom}</span>
        <dl className="submission-specs">
          {SPEC_FIELDS.map(([key, label]) => (
            <div key={key}><dt>{label}</dt><dd>{row.specifications[key] ?? "—"}</dd></div>
          ))}
        </dl>
        <span>{formatMoney(row.askingPrice, 4)} / {row.uom.toLowerCase()} · Minimum {row.minimumQuantity}{row.availability === "limited" && row.maximumQuantity ? ` · Available up to ${row.maximumQuantity}` : ""} · {titleCase(row.availability)} · Proposed code {row.proposedCode}</span>
      </div>
      <div className="submission-decision">
        <label>Catalogue code<Input aria-label={`Catalogue code for ${row.proposedCode}`} value={code} onChange={(event) => setCode(event.target.value)} /></label>
        <label>Rejection note<Input aria-label={`Rejection note for ${row.proposedCode}`} value={note} placeholder="Required only if you reject" onChange={(event) => setNote(event.target.value)} /></label>
        <div className="submission-decision__actions">
          <Button disabled={busy || !code.trim()} onClick={() => void decide(true)}>Accept</Button>
          <Button variant="secondary" disabled={busy || !note.trim()} onClick={() => void decide(false)}>Reject</Button>
        </div>
        {error ? <p className="negative">{error}</p> : null}
      </div>
    </article>
  );
}

export function SubmissionQueue() {
  const submissions = useApiQuery("admin-submissions", (signal) => listAdminSubmissions(signal));
  const rows = submissions.data ?? [];
  return (
    <section className="section-block data-section submission-queue" style={{ marginBottom: 16 }}>
      <div className="step-label"><span>01</span><div><strong>Product submissions</strong><small>Accepting adds the product to the catalogue and lists the supplier’s asking price. Rejecting leaves the catalogue unchanged.</small></div></div>
      <AsyncContent isLoading={submissions.isLoading && !submissions.data} error={submissions.error} onRetry={submissions.reload} isEmpty={Boolean(submissions.data) && rows.length === 0} emptyTitle="No products waiting" emptyMessage="Supplier submissions appear here until you accept or reject them." loadingLabel="Loading submissions…">
        <div>{rows.map((row) => <ReviewRow key={row.id} row={row} onDone={submissions.reload} />)}</div>
      </AsyncContent>
    </section>
  );
}
