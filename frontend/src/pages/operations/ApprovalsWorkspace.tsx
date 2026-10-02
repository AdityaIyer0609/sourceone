import { useState } from "react";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Badge, Button } from "../../components/ui";
import { approveOrderRequest, declineOrderRequest, listApprovals, rejectDeal, type ApprovalStatus } from "../../lib/api/approvals";
import { getErrorMessage } from "../../lib/api/client";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatDateTime, formatMoney, titleCase } from "../../lib/pricingFormat";

const TONE: Record<ApprovalStatus, "neutral" | "positive" | "warning" | "negative" | "info"> = {
  pending: "warning",
  approved: "positive",
  declined: "neutral",
  deal_rejected: "negative",
};

export function ApprovalsWorkspace() {
  const queue = useApiQuery("order-approvals", (signal) => listApprovals(signal));
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const rows = queue.data ?? [];

  const act = async (id: string, run: (id: string) => Promise<unknown>) => {
    setBusyId(id);
    setError(null);
    try {
      await run(id);
      queue.reload();
    } catch (cause) {
      setError(getErrorMessage(cause));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      {error && <p className="negative" role="alert">{error}</p>}
      <AsyncContent isLoading={queue.isLoading && !queue.data} error={queue.error} onRetry={queue.reload} isEmpty={Boolean(queue.data) && rows.length === 0} emptyTitle="No approval requests" emptyMessage="New orders are placed directly. Nothing is waiting for approval." loadingLabel="Loading approvals…">
        <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Request</th><th>Material total</th><th>Threshold</th><th>Submitted</th><th>Decision</th><th/></tr></thead><tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td><strong>{row.negotiationNumber}</strong><small>{row.productName}</small></td>
              <td>{formatMoney(row.amount, 2)}</td>
              <td>{formatMoney(row.threshold, 2)}</td>
              <td><small>{row.submittedBy}<br />{formatDateTime(row.createdAt)}</small></td>
              <td><Badge tone={TONE[row.status]}>{titleCase(row.status)}</Badge>{row.decidedBy && <small>{row.decidedBy}{row.decisionNote ? ` · ${row.decisionNote}` : ""}</small>}</td>
              <td>
                {row.status === "pending" && (
                  <>
                    <Button disabled={busyId === row.id} onClick={() => void act(row.id, approveOrderRequest)}>Approve</Button>
                    <Button variant="secondary" disabled={busyId === row.id} onClick={() => void act(row.id, (id) => declineOrderRequest(id))}>Decline</Button>
                    <Button variant="ghost" disabled={busyId === row.id} onClick={() => void act(row.id, (id) => rejectDeal(id, "Approver rejected the deal"))}>Reject deal</Button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody></table></div>
      </AsyncContent>
    </>
  );
}
