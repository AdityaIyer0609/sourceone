import { Search } from "lucide-react";
import { useState } from "react";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Badge, Button, Input } from "../../components/ui";
import { getErrorMessage } from "../../lib/api/client";
import {
  createAdminProduct, listAdminProducts, mapProductSeries, setAdminProductActive, setProductSeriesActive, updateAdminProduct,
  type AdminProduct, type ProductEdit,
} from "../../lib/api/catalogue";
import { listRateSeries } from "../../lib/api/pricing";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { listAdminDocuments, setProductDocumentActive, uploadProductDocument } from "../../lib/api/productContent";
import { titleCase } from "../../lib/pricingFormat";

const SPEC_FIELDS = [
  ["grade", "Grade"], ["producer", "Producer"], ["mfi", "MFI"],
  ["density", "Density"], ["application", "Application"], ["quality", "Quality"],
] as const;
const EMPTY_SPECS = Object.fromEntries(SPEC_FIELDS.map(([key]) => [key, ""]));
const EMPTY = { productCode: "", name: "", category: "", subcategory: "", description: "", uom: "KG", isActive: true, specifications: { ...EMPTY_SPECS } };

function ProductDocuments({ productCode }: { productCode: string }) {
  const documents = useApiQuery(`admin-docs:${productCode}`, (signal) => listAdminDocuments(productCode, signal));
  const [name, setName] = useState("");
  const [documentType, setDocumentType] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await uploadProductDocument(productCode, { name, documentType, file });
      setName("");
      setDocumentType("");
      setFile(null);
      documents.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      <div className="form-grid">
        <label>Document name<Input aria-label="Document name" value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label>Document type<Input aria-label="Document type" value={documentType} onChange={(event) => setDocumentType(event.target.value)} /></label>
        <label>File<Input aria-label="Document file" type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label>
        <label>Upload<Button variant="secondary" disabled={busy || !name.trim() || !documentType.trim() || !file} onClick={() => void upload()}>{busy ? "Uploading…" : "Upload document"}</Button></label>
      </div>
      {(documents.data ?? []).map((document) => (
        <p key={document.id}><small>{document.documentType} · {document.filename} · {document.isActive ? "Active" : "Inactive"}</small> {document.name} <Button variant="ghost" onClick={() => void setProductDocumentActive(productCode, document.id, !document.isActive).then(() => documents.reload()).catch((cause) => setError(getErrorMessage(cause)))}>{document.isActive ? "Deactivate" : "Activate"}</Button></p>
      ))}
      {documents.data && documents.data.length === 0 && <p><small>No documents are on file for this product.</small></p>}
      {error && <p className="negative">{error}</p>}
    </div>
  );
}

export function ItemMasterWorkspace() {
  const products = useApiQuery("item-master", (signal) => listAdminProducts(signal));
  const series = useApiQuery("item-master-series", (signal) => listRateSeries(signal));
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState<"all" | "active" | "inactive">("all");
  const [draft, setDraft] = useState(EMPTY);
  const [editing, setEditing] = useState<string | null>(null);
  const [seriesCode, setSeriesCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const rows = products.data ?? [];
  const categories = [...new Set(rows.map((row) => row.category))].sort();
  const term = search.trim().toLowerCase();
  const visible = rows.filter((row) => {
    const haystack = [row.productCode, row.name, row.category, row.subcategory, row.description].join(" ").toLowerCase();
    if (term && !haystack.includes(term)) return false;
    if (category && row.category !== category) return false;
    if (status === "active" && !row.isActive) return false;
    if (status === "inactive" && row.isActive) return false;
    return true;
  });
  const selected = rows.find((row) => row.productCode === editing) ?? null;
  const unavailable = { "aria-disabled": "true" as const, title: "Not available yet" };

  const save = async () => {
    setBusy(true);
    setError(null);
    const specifications = {
      ...Object.fromEntries((selected?.specifications ?? []).filter((field) => field.value && !SPEC_FIELDS.some(([key]) => key === field.key) && field.key !== "uom" && field.key !== "description").map((field) => [field.key, field.value])),
      ...draft.specifications,
    };
    const edit: ProductEdit = {
      name: draft.name, category: draft.category,
      subcategory: draft.subcategory || null, description: draft.description || null, specifications,
    };
    try {
      if (editing) await updateAdminProduct(editing, edit);
      else await createAdminProduct({ ...draft, specifications });
      setDraft(EMPTY);
      setEditing(null);
      products.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  const edit = (row: AdminProduct) => {
    setEditing(row.productCode);
    setDraft({
      productCode: row.productCode, name: row.name, category: row.category,
      subcategory: row.subcategory ?? "", description: row.description ?? "", uom: row.uom, isActive: row.isActive,
      specifications: { ...EMPTY_SPECS, ...Object.fromEntries(row.specifications.flatMap((field) => field.value ? [[field.key, field.value]] : [])) },
    });
    setSeriesCode("");
    setError(null);
  };

  const toggle = async (row: AdminProduct) => {
    setError(null);
    try {
      await setAdminProductActive(row.productCode, !row.isActive);
      products.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    }
  };

  const addSeries = async () => {
    if (!editing || !seriesCode) return;
    setError(null);
    try {
      await mapProductSeries(editing, seriesCode);
      setSeriesCode("");
      products.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    }
  };

  const toggleSeries = async (code: string, active: boolean) => {
    if (!editing) return;
    setError(null);
    try {
      await setProductSeriesActive(editing, code, !active);
      products.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    }
  };

  return (
    <>
      <div className="metric-row">
        {[
          ["ACTIVE", rows.filter((row) => row.isActive).length, "Sellable products"],
          ["INACTIVE", rows.filter((row) => !row.isActive).length, "Hidden from buyers"],
          ["RATE ON REQUEST", rows.filter((row) => row.benchmarkStatus === "rate_on_request").length, "No current benchmark"],
          ["WITH LISTINGS", rows.filter((row) => row.listingCount > 0).length, "Supplier availability"],
        ].map(([label, value, note]) => <div key={String(label)}><small>{label}</small><strong>{String(value).padStart(2, "0")}</strong><span>{note}</span></div>)}
      </div>
      <section className="section-block" style={{ marginBottom: 16, padding: 16 }}>
        <div className="form-grid">
          <label>Product code<Input aria-label="Product code" value={draft.productCode} disabled={Boolean(editing)} onChange={(event) => setDraft({ ...draft, productCode: event.target.value })} /></label>
          <label>Name<Input aria-label="Name" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
          <label>Category<Input aria-label="Category" value={draft.category} onChange={(event) => setDraft({ ...draft, category: event.target.value })} /></label>
          <label>Subcategory<Input aria-label="Subcategory" value={draft.subcategory} onChange={(event) => setDraft({ ...draft, subcategory: event.target.value })} /></label>
          <label>Description<Input aria-label="Description" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
          <label>UOM<Input aria-label="UOM" value={draft.uom} disabled={Boolean(editing)} onChange={(event) => setDraft({ ...draft, uom: event.target.value })} /></label>
          {SPEC_FIELDS.map(([key, label]) => <label key={key}>{label}<Input aria-label={label} value={draft.specifications[key] ?? ""} placeholder="Not specified" onChange={(event) => setDraft({ ...draft, specifications: { ...draft.specifications, [key]: event.target.value } })} /></label>)}
        </div>
        {editing && selected && (
          <div className="form-grid">
            <label>Benchmark series
              <select className="input" aria-label="Benchmark series" value={seriesCode} onChange={(event) => setSeriesCode(event.target.value)}>
                <option value="">Choose a rate series</option>
                {(series.data ?? []).map((item) => <option key={item.id} value={item.code}>{item.code} · {item.displayName}</option>)}
              </select>
            </label>
            <label>Mapping<Button variant="secondary" disabled={!seriesCode} onClick={() => void addSeries()}>Map series</Button></label>
          </div>
        )}
        {selected && selected.series.map((item) => (
          <p key={item.seriesCode}><small>{item.seriesCode} · {item.displayName} · {item.currency} · {item.isActive ? titleCase(item.availability) : "Mapping inactive"}</small> <Button variant="ghost" onClick={() => void toggleSeries(item.seriesCode, item.isActive)}>{item.isActive ? "Unmap" : "Restore mapping"}</Button></p>
        ))}
        {editing && <ProductDocuments productCode={editing} />}
        {error && <p className="negative">{error}</p>}
        <div className="modal-actions">
          <Button disabled={busy || !draft.name || !draft.category || (!editing && !draft.productCode)} onClick={() => void save()}>{editing ? "Save product" : "Add product"}</Button>
          {editing && <Button variant="secondary" onClick={() => { setEditing(null); setDraft(EMPTY); }}>Cancel edit</Button>}
        </div>
      </section>
      <section className="section-block data-section">
        <div className="data-toolbar">
          <label className="search-box search-box--small"><Search size={17}/><Input placeholder="Search item master…" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
          <div>
            <select className="input" aria-label="Category" value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="">All categories</option>
              {categories.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select className="input" aria-label="Status" value={status} onChange={(event) => setStatus(event.target.value as "all" | "active" | "inactive")}>
              <option value="all">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
            <Button variant="secondary" {...unavailable}>Export</Button>
          </div>
        </div>
        <AsyncContent isLoading={products.isLoading && !products.data} error={products.error} onRetry={products.reload} isEmpty={Boolean(products.data) && visible.length === 0} emptyTitle="No products" emptyMessage="Add a SourceOne product to sell it." loadingLabel="Loading products…">
          <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Product code</th><th>Name / category</th><th>UOM</th><th>Benchmark</th><th>Listings</th><th>Status</th><th/></tr></thead><tbody>{visible.map((row) => (
            <tr key={row.productCode} onClick={() => edit(row)} style={{ cursor: "pointer" }}>
              <td><strong>{row.productCode}</strong><small>{row.subcategory ?? "—"}</small></td>
              <td><strong>{row.name}</strong><small>{row.category}{row.description ? ` · ${row.description}` : ""}</small></td>
              <td>{row.uom}</td>
              <td><Badge tone={row.benchmarkStatus === "available" ? "positive" : "warning"}>{row.benchmarkStatus === "available" ? "BENCHMARK" : "RATE ON REQUEST"}</Badge><small>{row.series.filter((item) => item.isActive).map((item) => item.seriesCode).join(", ") || "No series"}</small></td>
              <td><strong>{row.listingCount}</strong><small>{row.listingCount ? "Suppliers listing" : "No active listing"}</small></td>
              <td><Badge tone={row.isActive ? "positive" : "neutral"}>{row.isActive ? "ACTIVE" : "INACTIVE"}</Badge></td>
              <td><Button variant="ghost" onClick={(event) => { event.stopPropagation(); void toggle(row); }}>{row.isActive ? "Deactivate" : "Activate"}</Button></td>
            </tr>
          ))}</tbody></table></div>
        </AsyncContent>
      </section>
    </>
  );
}
