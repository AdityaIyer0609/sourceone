import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Badge } from "../../components/ui";
import { getCompany } from "../../lib/api/approvals";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { titleCase } from "../../lib/pricingFormat";

export function CompanyWorkspace() {
  const company = useApiQuery("company", (signal) => getCompany(signal));
  const data = company.data;

  return (
    <AsyncContent isLoading={company.isLoading && !data} error={company.error} onRetry={company.reload} loadingLabel="Loading company…">
      {data && (
        <>
          <section className="section-block" style={{ marginBottom: 16, padding: 16 }}>
            <p>Anyone who can place an order in {data.name} places it at any material total. There is no approval threshold.</p>
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
