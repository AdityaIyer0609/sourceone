import { Button } from "../ui";
import { OrgLink } from "../supplier/OrgLink";
import type { SupplierMatch } from "../../lib/api/listings";
import { formatMoney, orderCharges, previewOrderTotal, titleCase } from "../../lib/pricingFormat";
import { tradeDecision } from "../../lib/tradeDecision";

function orgName(name: string) {
  return name.replace(/\s*\(demo supplier\)\s*$/i, "");
}

function basisLabel(basis: SupplierMatch["comparison"]["basis"]) {
  if (basis === "lane") return "Saved lane";
  if (basis === "per_km") return "Rate per km";
  return "Freight not set";
}

function quote(match: SupplierMatch, quantity: number, unit: string) {
  const material = previewOrderTotal(String(quantity), { amount: unit, currency: match.askingPrice.currency });
  const freight = match.comparison.freight;
  const charges = orderCharges(material, freight);
  return { material, freight, charges };
}

export function SupplierComparison({ matches, pin, quantity, uom, buyerPrice, baseline, several, busySupplier, onPlace, onNegotiate, onAsk }: {
  matches: SupplierMatch[];
  pin: string;
  quantity: number;
  uom: string;
  buyerPrice: string;
  baseline: string;
  several: boolean;
  busySupplier: string | null;
  onPlace: (supplierUserId: string) => void;
  onNegotiate: (supplierUserId: string, offeredPrice: string) => void;
  onAsk: (supplierUserId: string) => void;
}) {
  const shortlist = matches.filter((match) => match.comparison.place != null).sort((a, b) => (a.comparison.place ?? 0) - (b.comparison.place ?? 0));
  const actionFor = (match: SupplierMatch) => {
    const choice = tradeDecision(match, quantity, buyerPrice, baseline, several);
    const figures = quote(match, quantity, choice.unit || match.askingPrice.amount);
    return { ...choice, ...figures };
  };
  const button = (match: SupplierMatch, choice: ReturnType<typeof actionFor>) => {
    const name = orgName(match.organisation);
    const busy = busySupplier === match.supplierUserId;
    if (choice.action === "ask") return <Button disabled={busy} onClick={() => onAsk(match.supplierUserId)}>Ask {name}</Button>;
    if (choice.action === "place") return <Button disabled={busy || !(Number(choice.unit) > 0)} onClick={() => onPlace(match.supplierUserId)}>Place order</Button>;
    return <Button variant="secondary" disabled={busy || !(Number(choice.unit) > 0)} onClick={() => onNegotiate(match.supplierUserId, choice.unit)}>Negotiate</Button>;
  };
  return (
    <section className="supplier-compare">
      <header>
        <small>Compared for {pin}</small>
        <strong>{shortlist.length ? `${shortlist.length} to consider` : "No freight to compare"}</strong>
        <p>Each supplier shows the material, freight, GST, and payable estimate for {quantity.toLocaleString("en-IN")} {uom.toLowerCase()} before you place an order or negotiate. Payable is an estimate. The order stores the material value.</p>
      </header>
      {shortlist.length > 0 && (
        <div className="supplier-compare__short">
          {shortlist.map((match) => {
            const choice = actionFor(match);
            return (
              <article key={match.supplierUserId}>
                <small>0{match.comparison.place}</small>
                <strong><OrgLink organisationId={match.organisationId}>{orgName(match.organisation)}</OrgLink></strong>
                <span>{match.supplierName} · {titleCase(match.availability)}</span>
                <dl>
                  <div><dt>Asking price</dt><dd>{formatMoney(match.askingPrice)}</dd></div>
                  <div><dt>Material</dt><dd>{formatMoney(choice.material, 2)}</dd></div>
                  <div><dt>{basisLabel(match.comparison.basis)}</dt><dd>{choice.freight ? formatMoney(choice.freight) : "On request"}</dd></div>
                  <div><dt>GST 18%</dt><dd>{formatMoney(choice.charges.gst)}</dd></div>
                  <div><dt>Payable estimate</dt><dd>{formatMoney(choice.charges.payable)}</dd></div>
                </dl>
                <ul>{match.comparison.notes.map((note) => <li key={note}>{note}</li>)}</ul>
                {button(match, choice)}
              </article>
            );
          })}
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
                <th>Material</th>
                <th>Freight</th>
                <th>GST</th>
                <th>Payable estimate</th>
                <th>Supply</th>
                <th>History</th>
                <th/>
              </tr>
            </thead>
            <tbody>
              {matches.map((match) => {
                const choice = actionFor(match);
                return (
                  <tr key={match.supplierUserId}>
                    <td>
                      <strong><OrgLink organisationId={match.organisationId}>{orgName(match.organisation)}</OrgLink></strong>
                      <small>{match.supplierName}</small>
                    </td>
                    <td>{formatMoney(match.askingPrice)}</td>
                    <td>{formatMoney(choice.material, 2)}</td>
                    <td>{choice.freight ? formatMoney(choice.freight) : "On request"}<small>{basisLabel(match.comparison.basis)}</small></td>
                    <td>{formatMoney(choice.charges.gst)}</td>
                    <td>{formatMoney(choice.charges.payable)}</td>
                    <td>{titleCase(match.availability)}<small>{match.maximumQuantity ? `Available ${Number(match.maximumQuantity).toLocaleString("en-IN")}` : "No stock figure"} · MOQ {Number(match.minimumQuantity).toLocaleString("en-IN")} {match.uom.toLowerCase()}</small></td>
                    <td>{match.comparison.notes.map((note) => <small key={note}>{note}</small>)}</td>
                    <td>{button(match, choice)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
