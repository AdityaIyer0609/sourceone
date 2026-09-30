import { useEffect, useState } from "react";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Badge, Button, Input } from "../../components/ui";
import { getCompany, setCompanyThreshold } from "../../lib/api/approvals";
import { getErrorMessage } from "../../lib/api/client";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { titleCase } from "../../lib/pricingFormat";

export function CompanyWorkspace() {
  const company = useApiQuery("company", (signal) => getCompany(signal));
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const data = company.data;

  useEffect(() => {
    if (!data?.threshold) return;
    setAmount(Number(data.threshold.amount).toFixed(2));
    setCurrency(data.threshold.currency);
  }, [data]);

  const save = async (clear = false) => {
    setBusy(true);
    setError(null);
    try {
      await setCompanyThreshold(clear ? null : amount, clear ? null : currency);
      company.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AsyncContent isLoading={company.isLoading && !data} error={company.error} onRetry={company.reload} loadingLabel="Loading company…">
      {data && (
        <>
          <section className="section-block" style={{ marginBottom: 16, padding: 16 }}>
            <p>Orders above this material total wait for another person in {data.name}. Freight and GST are not part of the threshold.</p>
            <div className="form-grid">
              <label>Threshold amount<Input aria-label="Threshold amount" value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
              <label>Currency
                <select className="input" aria-label="Threshold currency" value={currency} onChange={(event) => setCurrency(event.target.value)}>
                  <option value="INR">INR</option>
                  <option value="USD">USD</option>
                </select>
              </label>
            </div>
            {error && <p className="negative">{error}</p>}
            <div className="modal-actions">
              <Button disabled={busy || !amount} onClick={() => void save(false)}>{busy ? "Saving…" : "Save threshold"}</Button>
              <Button variant="secondary" disabled={busy || !data.threshold} onClick={() => void save(true)}>Clear threshold</Button>
            </div>
          </section>
          {data.users && (
            <section className="section-block data-section">
              <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Name</th><th>Email</th><th>Roles</th><th>Status</th></tr></thead><tbody>
                {data.users.map((user) => (
                  <tr key={user.id}>
                    <td><strong>{user.fullName}</strong></td>
                    <td>{user.email}</td>
                    <td>{user.roles.map((role) => titleCase(role)).join(", ") || "—"}</td>
                    <td><Badge tone={user.isActive ? "positive" : "neutral"}>{user.isActive ? "ACTIVE" : "INACTIVE"}</Badge></td>
                  </tr>
                ))}
              </tbody></table></div>
            </section>
          )}
        </>
      )}
    </AsyncContent>
  );
}
