import { useState } from "react";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Badge, Button, Input } from "../../components/ui";
import { getErrorMessage } from "../../lib/api/client";
import { createFreightRule, listFreightRules, updateFreightRule, type FreightRule, type FreightRuleInput } from "../../lib/api/freight";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatMoney } from "../../lib/pricingFormat";

const EMPTY: FreightRuleInput = {
  originPin: "", originLabel: "", destinationPin: "", destinationLabel: "",
  ratePerKg: "", currency: "INR", minimumFreight: "", isActive: true,
  effectiveFrom: new Date().toISOString().slice(0, 10), effectiveTo: "",
};

function toInput(rule: FreightRule): FreightRuleInput {
  return {
    originPin: rule.originPin, originLabel: rule.originLabel,
    destinationPin: rule.destinationPin, destinationLabel: rule.destinationLabel,
    ratePerKg: rule.ratePerKg, currency: rule.currency,
    minimumFreight: rule.minimumFreight ?? "", isActive: rule.isActive,
    effectiveFrom: rule.effectiveFrom, effectiveTo: rule.effectiveTo ?? "",
  };
}

export function FreightManagement() {
  const rules = useApiQuery("freight-rules", (signal) => listFreightRules(signal));
  const [draft, setDraft] = useState<FreightRuleInput>(EMPTY);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof FreightRuleInput, value: string | boolean) => setDraft((current) => ({ ...current, [key]: value }));

  const save = async () => {
    setBusy(true);
    setError(null);
    const body: FreightRuleInput = {
      ...draft,
      minimumFreight: draft.minimumFreight ? draft.minimumFreight : null,
      effectiveTo: draft.effectiveTo ? draft.effectiveTo : null,
    };
    try {
      if (editing) await updateFreightRule(editing, body);
      else await createFreightRule(body);
      setDraft(EMPTY);
      setEditing(null);
      rules.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (rule: FreightRule) => {
    setError(null);
    try {
      await updateFreightRule(rule.id, { ...toInput(rule), isActive: !rule.isActive, minimumFreight: rule.minimumFreight, effectiveTo: rule.effectiveTo });
      rules.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    }
  };

  return (
    <AsyncContent isLoading={rules.isLoading && !rules.data} error={rules.error} onRetry={rules.reload} loadingLabel="Loading freight rules…">
      <section className="section-block" style={{ marginBottom: 16, padding: 16 }}>
        <div className="form-grid">
          <label>Origin<Input aria-label="Origin" value={draft.originLabel} onChange={(event) => set("originLabel", event.target.value)} placeholder="City" /></label>
          <label>Origin PIN<Input aria-label="Origin PIN" value={draft.originPin} onChange={(event) => set("originPin", event.target.value)} placeholder="6-digit PIN" /></label>
          <label>Destination<Input aria-label="Destination" value={draft.destinationLabel} onChange={(event) => set("destinationLabel", event.target.value)} placeholder="City" /></label>
          <label>Destination PIN<Input aria-label="Destination PIN" value={draft.destinationPin} onChange={(event) => set("destinationPin", event.target.value)} placeholder="6-digit PIN" /></label>
          <label>Rate / kg<Input aria-label="Rate per kg" value={draft.ratePerKg} onChange={(event) => set("ratePerKg", event.target.value)} placeholder="1.2500" /></label>
          <label>Currency
            <select className="input" aria-label="Currency" value={draft.currency} onChange={(event) => set("currency", event.target.value)}>
              <option value="INR">INR</option>
              <option value="USD">USD</option>
            </select>
          </label>
          <label>Minimum freight<Input aria-label="Minimum freight" value={draft.minimumFreight ?? ""} onChange={(event) => set("minimumFreight", event.target.value)} placeholder="Optional" /></label>
          <label>Effective from<Input aria-label="Effective from" type="date" value={draft.effectiveFrom} onChange={(event) => set("effectiveFrom", event.target.value)} /></label>
          <label>Effective to<Input aria-label="Effective to" type="date" value={draft.effectiveTo ?? ""} onChange={(event) => set("effectiveTo", event.target.value)} /></label>
          <label>Status
            <select className="input" aria-label="Active" value={draft.isActive ? "active" : "inactive"} onChange={(event) => set("isActive", event.target.value === "active")}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </label>
        </div>
        {error && <p className="negative">{error}</p>}
        <div className="modal-actions">
          <Button disabled={busy} onClick={() => void save()}>{editing ? "Save rule" : "Add rule"}</Button>
          {editing && <Button variant="secondary" onClick={() => { setEditing(null); setDraft(EMPTY); }}>Cancel edit</Button>}
        </div>
      </section>
      <section className="section-block data-section">
        <div className="market-table-wrap">
          <table className="market-table">
            <thead><tr><th>Origin</th><th>Destination</th><th>Rate</th><th>Minimum</th><th>Effective</th><th>Status</th><th/></tr></thead>
            <tbody>
              {(rules.data ?? []).map((rule) => (
                <tr key={rule.id}>
                  <td><strong>{rule.originLabel}</strong><small>{rule.originPin}</small></td>
                  <td><strong>{rule.destinationLabel}</strong><small>{rule.destinationPin}</small></td>
                  <td><strong>{formatMoney({ amount: rule.ratePerKg, currency: rule.currency }, 4)}</strong><small>/ kg</small></td>
                  <td><strong>{rule.minimumFreight ? formatMoney({ amount: rule.minimumFreight, currency: rule.currency }) : "—"}</strong></td>
                  <td><small>{rule.effectiveFrom}{rule.effectiveTo ? ` – ${rule.effectiveTo}` : ""}</small></td>
                  <td><Badge tone={rule.isActive ? "positive" : "neutral"}>{rule.isActive ? "ACTIVE" : "INACTIVE"}</Badge></td>
                  <td>
                    <Button variant="ghost" onClick={() => { setEditing(rule.id); setDraft(toInput(rule)); }}>Edit</Button>
                    <Button variant="ghost" onClick={() => void toggle(rule)}>{rule.isActive ? "Deactivate" : "Activate"}</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </AsyncContent>
  );
}
