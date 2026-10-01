import { useState } from "react";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Button, Input } from "../../components/ui";
import { getErrorMessage } from "../../lib/api/client";
import { readSupplierFreight, removeSupplierLane, saveDispatch, saveSupplierKmRate, saveSupplierLane } from "../../lib/api/supplierFreight";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatMoney } from "../../lib/pricingFormat";

export function SupplierFreightWorkspace() {
  const freight = useApiQuery("supplier-freight", (signal) => readSupplierFreight(signal));
  const data = freight.data;
  const [pin, setPin] = useState("");
  const [place, setPlace] = useState("");
  const [destinationPin, setDestinationPin] = useState("");
  const [destination, setDestination] = useState("");
  const [rate, setRate] = useState("");
  const [minimum, setMinimum] = useState("");
  const [kmRate, setKmRate] = useState("");
  const [kmMinimum, setKmMinimum] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      freight.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const dispatchPin = pin || data?.dispatchPin || "";
  const dispatchPlace = place || data?.dispatchLabel || "";
  return (
    <AsyncContent isLoading={freight.isLoading && !data} error={freight.error} onRetry={freight.reload} loadingLabel="Loading your freight…">
      {data && (
        <div className="supplier-freight">
          <section className="section-block" style={{ padding: 16, marginBottom: 16 }}>
            <div className="step-label"><span>01</span><div><strong>Dispatch PIN</strong><small>Lanes start from this PIN. It is your origin, not a buyer’s delivery PIN.</small></div></div>
            <div className="form-grid">
              <label>PIN<Input aria-label="Dispatch PIN" value={dispatchPin} onChange={(event) => setPin(event.target.value)} /></label>
              <label>Place<Input aria-label="Dispatch place" value={dispatchPlace} onChange={(event) => setPlace(event.target.value)} /></label>
            </div>
            <div className="modal-actions">
              <Button disabled={busy || !/^[1-9][0-9]{5}$/.test(dispatchPin) || !dispatchPlace.trim()} onClick={() => void run(() => saveDispatch({ pin: dispatchPin, label: dispatchPlace.trim() }))}>Save dispatch PIN</Button>
            </div>
          </section>
          <section className="section-block" style={{ padding: 16, marginBottom: 16 }}>
            <div className="step-label"><span>02</span><div><strong>Saved lanes</strong><small>A rate per kg for one destination. This is used when the buyer’s PIN matches. It does not change your asking price.</small></div></div>
            <div className="form-grid">
              <label>Destination PIN<Input aria-label="Destination PIN" value={destinationPin} onChange={(event) => setDestinationPin(event.target.value)} /></label>
              <label>Place<Input aria-label="Destination place" value={destination} onChange={(event) => setDestination(event.target.value)} /></label>
              <label>Rate per kg<Input aria-label="Rate per kg" value={rate} onChange={(event) => setRate(event.target.value)} /></label>
              <label>Minimum freight<Input aria-label="Lane minimum freight" value={minimum} placeholder="Optional" onChange={(event) => setMinimum(event.target.value)} /></label>
            </div>
            <div className="modal-actions">
              <Button disabled={busy || !data.dispatchPin || !/^[1-9][0-9]{5}$/.test(destinationPin) || !destination.trim() || !(Number(rate) > 0)} onClick={() => void run(async () => {
                await saveSupplierLane({
                  destinationPin, destinationLabel: destination.trim(), ratePerKg: rate, currency: "INR",
                  minimumFreight: minimum.trim() ? minimum : null,
                });
                setDestinationPin("");
                setDestination("");
                setRate("");
                setMinimum("");
              })}>Save lane</Button>
            </div>
            {data.lanes.length > 0 && (
              <table className="market-table"><thead><tr><th>From</th><th>To</th><th>Rate</th><th>Minimum</th><th/></tr></thead><tbody>
                {data.lanes.map((lane) => (
                  <tr key={lane.id}>
                    <td>{lane.originPin}</td>
                    <td><strong>{lane.destinationLabel}</strong><small>{lane.destinationPin}</small></td>
                    <td>{formatMoney({ amount: lane.ratePerKg, currency: lane.currency }, 4)} / kg</td>
                    <td>{lane.minimumFreight ? formatMoney({ amount: lane.minimumFreight, currency: lane.currency }) : "—"}</td>
                    <td><Button variant="ghost" disabled={busy} onClick={() => void run(() => removeSupplierLane(lane.id))}>Remove</Button></td>
                  </tr>
                ))}
              </tbody></table>
            )}
          </section>
          <section className="section-block" style={{ padding: 16 }}>
            <div className="step-label"><span>03</span><div><strong>Rate per km</strong><small>If you fill this in, it is used only when the destination does not match a saved lane and a road distance can be measured.</small></div></div>
            <div className="form-grid">
              <label>Rate per km<Input aria-label="Rate per km" value={kmRate || data.kmRate?.ratePerKm || ""} onChange={(event) => setKmRate(event.target.value)} /></label>
              <label>Minimum freight<Input aria-label="Per km minimum freight" value={kmMinimum || data.kmRate?.minimumFreight || ""} placeholder="Optional" onChange={(event) => setKmMinimum(event.target.value)} /></label>
            </div>
            <div className="modal-actions">
              <Button disabled={busy || !(Number(kmRate || data.kmRate?.ratePerKm) > 0)} onClick={() => void run(() => saveSupplierKmRate({
                ratePerKm: kmRate || data.kmRate?.ratePerKm || "",
                currency: "INR",
                minimumFreight: (kmMinimum || data.kmRate?.minimumFreight || "").trim() ? (kmMinimum || data.kmRate?.minimumFreight || "") : null,
              }))}>Save rate per km</Button>
            </div>
          </section>
          {error && <p className="negative">{error}</p>}
        </div>
      )}
    </AsyncContent>
  );
}
