import { Search } from "lucide-react";
import { useState } from "react";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Badge, Button, Input } from "../../components/ui";
import { getErrorMessage } from "../../lib/api/client";
import { createAdminUser, listAdminUsers, setAdminUserActive, setAdminUserRole, USER_ROLES, type AdminUser } from "../../lib/api/users";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { titleCase } from "../../lib/pricingFormat";

const EMPTY = { fullName: "", email: "", password: "", role: "buyer", organisationId: "" };

export function UsersWorkspace() {
  const users = useApiQuery("admin-users", (signal) => listAdminUsers(signal));
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const rows = users.data ?? [];
  const term = search.trim().toLowerCase();
  const visible = rows.filter((row) => [row.fullName, row.email, row.organisation, ...row.roles].join(" ").toLowerCase().includes(term));
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await createAdminUser({ ...draft, organisationId: draft.organisationId || undefined });
      setDraft(EMPTY);
      users.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const toggle = async (row: AdminUser) => {
    setError(null);
    try {
      await setAdminUserActive(row.id, !row.isActive);
      users.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    }
  };
  const changeRole = async (row: AdminUser, role: string) => {
    if (!role || row.roles[0] === role) return;
    setError(null);
    try {
      await setAdminUserRole(row.id, role);
      users.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    }
  };
  return (
    <>
      <div className="metric-row">
        {[
          ["USERS", rows.filter((row) => !row.isSystem).length, "Sign-in accounts"],
          ["ACTIVE", rows.filter((row) => row.isActive && !row.isSystem).length, "Can sign in"],
          ["INACTIVE", rows.filter((row) => !row.isActive).length, "Cannot sign in"],
          ["SYSTEM", rows.filter((row) => row.isSystem).length, "Never signs in"],
        ].map(([label, value, note]) => <div key={String(label)}><small>{label}</small><strong>{String(value).padStart(2, "0")}</strong><span>{note}</span></div>)}
      </div>
      <section className="section-block" style={{ marginBottom: 16, padding: 16 }}>
        <div className="form-grid">
          <label>Name<Input aria-label="Name" value={draft.fullName} onChange={(event) => setDraft({ ...draft, fullName: event.target.value })} /></label>
          <label>Email<Input aria-label="Email" value={draft.email} onChange={(event) => setDraft({ ...draft, email: event.target.value })} /></label>
          <label>Password<Input aria-label="Password" type="password" value={draft.password} onChange={(event) => setDraft({ ...draft, password: event.target.value })} /></label>
          <label>Role
            <select className="input" aria-label="Role" value={draft.role} onChange={(event) => setDraft({ ...draft, role: event.target.value })}>
              {USER_ROLES.map((role) => <option key={role} value={role}>{titleCase(role)}</option>)}
            </select>
          </label>
          {draft.role === "approver" && (
            <label>Buyer company
              <select className="input" aria-label="Buyer company" value={draft.organisationId} onChange={(event) => setDraft({ ...draft, organisationId: event.target.value })}>
                <option value="">New company</option>
                {[...new Map(rows.filter((row) => row.organisationType === "buyer").map((row) => [row.organisationId, row.organisation])).entries()].map(([id, name]) => <option key={id} value={id}>{name}</option>)}
              </select>
            </label>
          )}
        </div>
        {error && <p className="negative">{error}</p>}
        <div className="modal-actions">
          <Button disabled={busy || !draft.fullName || !draft.email || draft.password.length < 8} onClick={() => void save()}>{busy ? "Saving…" : "Add user"}</Button>
        </div>
      </section>
      <section className="section-block data-section">
        <div className="data-toolbar">
          <label className="search-box search-box--small"><Search size={17}/><Input placeholder="Search users…" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        </div>
        <AsyncContent isLoading={users.isLoading && !users.data} error={users.error} onRetry={users.reload} isEmpty={Boolean(users.data) && visible.length === 0} emptyTitle="No users" emptyMessage="Add a Plenza user to give them a role." loadingLabel="Loading users…">
          <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Name</th><th>Email</th><th>Organisation</th><th>Role</th><th>Status</th><th/></tr></thead><tbody>{visible.map((row) => (
            <tr key={row.id}>
              <td><strong>{row.fullName}</strong></td>
              <td>{row.email}</td>
              <td>{row.organisation}</td>
              <td>{row.isSystem ? <small>System</small> : <select className="input" aria-label={`Role for ${row.email}`} value={row.roles[0] ?? ""} onChange={(event) => void changeRole(row, event.target.value)}>{USER_ROLES.map((role) => <option key={role} value={role}>{titleCase(role)}</option>)}</select>}</td>
              <td><Badge tone={row.isActive ? "positive" : "neutral"}>{row.isActive ? "ACTIVE" : "INACTIVE"}</Badge></td>
              <td>{!row.isSystem && <Button variant="ghost" onClick={() => void toggle(row)}>{row.isActive ? "Deactivate" : "Activate"}</Button>}</td>
            </tr>
          ))}</tbody></table></div>
        </AsyncContent>
      </section>
    </>
  );
}