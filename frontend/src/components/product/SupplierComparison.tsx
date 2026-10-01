import { Button } from "../ui";
import { OrgLink } from "../supplier/OrgLink";
import type { SupplierMatch } from "../../lib/api/listings";
import { formatMoney, titleCase } from "../../lib/pricingFormat";

function orgName(name: string) {
  return name.replace(/\s*\(demo supplier\)\s*$/i, "");
}

function basisLabel(basis: SupplierMatch["comparison"]["basis"]) {
  if (basis === "lane") return "Saved lane";
  if (basis === "per_km") return "Rate per km";
  return "Freight not set";
}

export function SupplierComparison({ matches, pin, quantity, uom, onAsk }: {
  matches: SupplierMatch[];
  pin: string;
  quantity: number;
  uom: string;
  onAsk: (supplierUserId: string) => void;
}) {
  const shortlist = matches.filter((match) => match.comparison.place != null).sort((a, b) => (a.comparison.place ?? 0) - (b.comparison.place ?? 0));
  return (
    <section className="supplier-compare">
      <header>
        <small>Compared for {pin}</small>
        <strong>{shortlist.length ? `${shortlist.length} to consider` : "No freight to compare"}</strong>
        <p>Every supplier who lists this product is below. The short list is the lowest estimated total for {quantity.toLocaleString("en-IN")} {uom.toLowerCase()}, using each supplier’s own freight. A saved lane is used when this PIN matches. Their rate per km is used only when it does not. History moves the order by at most 5% in their favour or 25% against them, and only when the sample is large enough. The figures on the card are the real estimate.</p>
      </header>
      {shortlist.length > 0 && (
        <div className="supplier-compare__short">
          {shortlist.map((match) => (
            <article key={match.supplierUserId}>
              <small>0{match.comparison.place}</small>
              <strong><OrgLink organisationId={match.organisationId}>{match.organisation.replace(/\s*\(demo supplier\)\s*$/i, "")}</OrgLink></strong>
              <span>{match.supplierName} · {titleCase(match.availability)}</span>
              <dl>
                <div><dt>Asking price</dt><dd>{formatMoney(match.askingPrice)}</dd></div>
                <div><dt>{basisLabel(match.comparison.basis)}</dt><dd>{match.comparison.freight ? formatMoney(match.comparison.freight) : "—"}</dd></div>
                <div><dt>Estimated total</dt><dd>{match.comparison.landed ? formatMoney(match.comparison.landed, 2) : "—"}</dd></div>
              </dl>
              <ul>{match.comparison.notes.map((note) => <li key={note}>{note}</li>)}</ul>
              {match.availability === "on_request" && <Button onClick={() => onAsk(match.supplierUserId)}>Ask {orgName(match.organisation)}</Button>}
            </article>
          ))}
        </div>
      )}
      <div className="supplier-compare__all section-block">
        <small>All suppliers</small>
        <div className="market-table-wrap">
          <table className="market-table">
            <thead>
              <tr>
                <th>Supplier</th>
                <th>Asking price</th>
                <th>Freight</th>
                <th>Estimated total</th>
                <th>Supply</th>
                <th>History</th>
                <th/>
              </tr>
            </thead>
            <tbody>
              {matches.map((match) => (
                <tr key={match.supplierUserId}>
                  <td>
                    <strong><OrgLink organisationId={match.organisationId}>{match.organisation.replace(/\s*\(demo supplier\)\s*$/i, "")}</OrgLink></strong>
                    <small>{match.supplierName}</small>
                  </td>
                  <td>{formatMoney(match.askingPrice)}</td>
                  <td>{match.comparison.freight ? formatMoney(match.comparison.freight) : "Not set"}<small>{basisLabel(match.comparison.basis)}</small></td>
                  <td>{match.comparison.landed ? formatMoney(match.comparison.landed, 2) : "—"}</td>
                  <td>{titleCase(match.availability)}<small>{match.meetsMinimum ? "Minimum met" : "Below minimum"} · {Number(match.minimumQuantity).toLocaleString("en-IN")} {match.uom.toLowerCase()}</small></td>
                  <td>{match.comparison.notes.map((note) => <small key={note}>{note}</small>)}</td>
                  <td>{match.availability === "on_request" ? <Button onClick={() => onAsk(match.supplierUserId)}>Ask {orgName(match.organisation)}</Button> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
