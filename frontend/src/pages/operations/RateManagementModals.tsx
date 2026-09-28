import { useState, type ReactNode } from "react";
import { ProductVisual } from "../../components/product/ProductVisual";
import { Badge, Button, Input, Modal } from "../../components/ui";
import { ApiError, getErrorMessage } from "../../lib/api/client";
import {
  createBenchmark,
  getSeriesTimeline,
  listAuditEvents,
  publishBenchmark,
  rejectBenchmark,
  submitBenchmark,
  withdrawBenchmark,
  type BenchmarkAdmin,
  type BenchmarkStatus,
  type RateSeries,
  type SourceRate,
} from "../../lib/api/pricing";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { BENCHMARK_GLYPH, formatDate, formatDateTime, formatMoney, titleCase } from "../../lib/pricingFormat";

const STATUS_TONES: Record<BenchmarkStatus, "neutral" | "positive" | "warning" | "negative" | "info"> = {
  draft: "info",
  submitted: "warning",
  published: "positive",
  rejected: "negative",
  withdrawn: "neutral",
};

export function StatusBadge({ status }: { status: BenchmarkStatus }) {
  return <Badge tone={STATUS_TONES[status]}>{status.toUpperCase()}</Badge>;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return <span><small>{label}</small><strong>{children}</strong></span>;
}

function ScrollBody({ children }: { children: ReactNode }) {
  return <div style={{ maxHeight: "62vh", overflowY: "auto" }}>{children}</div>;
}

function ActionError({ error }: { error: unknown }) {
  if (!error) return null;
  const code = error instanceof ApiError && error.code ? ` (${error.code})` : "";
  return <p className="negative" role="alert">{getErrorMessage(error)}{code}</p>;
}

function actorLine(who: string | null, at: string | null, extra?: string | null) {
  if (!at) return null;
  return `${who ?? "system"} · ${formatDateTime(at)}${extra ? ` · ${extra}` : ""}`;
}

export function BenchmarkModal({ benchmark: initial, onClose, onChanged }: { benchmark: BenchmarkAdmin; onClose: () => void; onChanged: () => void }) {
  const [benchmark, setBenchmark] = useState(initial);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const audit = useApiQuery(`audit:${benchmark.id}:${benchmark.rowVersion}:${benchmark.status}`, (signal) => listAuditEvents({ entityId: benchmark.id, limit: 20 }, signal));

  const run = async (action: () => Promise<BenchmarkAdmin>) => {
    setBusy(true);
    setError(null);
    try {
      setBenchmark(await action());
      setReason("");
      onChanged();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };

  const needsReason = benchmark.status !== "rejected" && benchmark.status !== "withdrawn";
  const input = benchmark.inputs.find((item) => item.role === "primary");
  const lifecycle: [string, string | null][] = [
    ["Created", actorLine(benchmark.createdBy, benchmark.createdAt)],
    ["Last edited", actorLine(benchmark.lastEditedBy, benchmark.lastEditedAt)],
    ["Submitted", actorLine(benchmark.submittedBy, benchmark.submittedAt)],
    ["Published", actorLine(benchmark.publishedBy, benchmark.publishedAt)],
    ["Rejected", actorLine(benchmark.rejectedBy, benchmark.rejectedAt, benchmark.rejectedReason)],
    ["Withdrawn", actorLine(benchmark.withdrawnBy, benchmark.withdrawnAt, benchmark.withdrawnReason)],
  ];

  return (
    <Modal open title="Benchmark review" onClose={onClose}>
      <ScrollBody>
        <div className="modal-product">
          <ProductVisual glyph={BENCHMARK_GLYPH} />
          <div>
            <strong>{benchmark.seriesCode}</strong>
            <small>{titleCase(benchmark.method)} · {benchmark.origin === "system_suggestion" ? "System suggestion" : "Human entry"}{benchmark.isEdited ? " · Edited" : ""}{benchmark.fourEyesRequired ? " · Four-eyes required" : " · Single publisher allowed"}</small>
          </div>
          <StatusBadge status={benchmark.status} />
        </div>
        <div className="modal-cost">
          <Row label="Source">{benchmark.primarySourceCode}</Row>
          {input && <Row label="Source rate">{input.sourceRowRef} · {input.rawProducer ?? "—"} · {formatDate(input.sourceAsOfDate)}</Row>}
          <Row label="Source as of">{formatDate(benchmark.sourceAsOfDate)}</Row>
          <Row label="Effective from">{formatDateTime(benchmark.effectiveFrom)}{benchmark.effectiveUntil ? ` → ${formatDateTime(benchmark.effectiveUntil)}` : ""}</Row>
          {benchmark.staleAfter && <Row label="Stale after">{formatDateTime(benchmark.staleAfter)} ({benchmark.stalenessDays} days)</Row>}
          {(benchmark.reason || benchmark.evidenceRef) && <Row label="Reason / evidence">{[benchmark.reason, benchmark.evidenceRef].filter(Boolean).join(" · ")}</Row>}
          {lifecycle.filter(([, value]) => value).map(([label, value]) => <Row key={label} label={label}>{value}</Row>)}
          <Row label={`Value (${benchmark.priceBasis}, ${benchmark.taxBasis})`}>{formatMoney(benchmark.value, 4)} / {benchmark.unit.toLowerCase()}</Row>
        </div>
        <div className="modal-product">
          <div>
            <strong>Audit trail</strong>
            {audit.isLoading && !audit.data && <small>Loading…</small>}
            {audit.error ? <small className="negative">{getErrorMessage(audit.error)}</small> : null}
            {audit.data?.map((event) => (
              <small key={event.id}>{formatDateTime(event.occurredAt)} · {titleCase(event.action)} by {event.actor ?? "system"}{event.fromStatus || event.toStatus ? ` · ${event.fromStatus ?? "—"} → ${event.toStatus ?? "—"}` : ""}{event.reason ? ` · ${event.reason}` : ""}</small>
            ))}
          </div>
        </div>
        {needsReason && <Input placeholder={benchmark.status === "published" ? "Reason (required to withdraw)" : "Reason (required to reject)"} value={reason} onChange={(event) => setReason(event.target.value)} />}
        <ActionError error={error} />
      </ScrollBody>
      <div className="modal-actions">
        <Button variant="secondary" onClick={onClose}>Close</Button>
        {benchmark.status === "draft" && <Button disabled={busy} onClick={() => run(() => submitBenchmark(benchmark.id))}>Submit</Button>}
        {(benchmark.status === "draft" || benchmark.status === "submitted") && <Button variant="secondary" disabled={busy} onClick={() => run(() => rejectBenchmark(benchmark.id, reason))}>Reject</Button>}
        {benchmark.status === "submitted" && <Button disabled={busy} onClick={() => run(() => publishBenchmark(benchmark.id))}>Publish</Button>}
        {benchmark.status === "published" && <Button variant="secondary" disabled={busy} onClick={() => run(() => withdrawBenchmark(benchmark.id, reason))}>Withdraw</Button>}
      </div>
    </Modal>
  );
}

export function SourceRateModal({ sourceRate, onClose, onCreated }: { sourceRate: SourceRate; onClose: () => void; onCreated: (benchmark: BenchmarkAdmin) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const selectable = sourceRate.resolutionStatus === "resolved" && sourceRate.isBenchmarkEligible;

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      onCreated(await createBenchmark({ mode: "select_source_rate", sourceRateId: sourceRate.id }));
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title="Source rate" onClose={onClose}>
      <ScrollBody>
        <div className="modal-product">
          <ProductVisual glyph={BENCHMARK_GLYPH} />
          <div><strong>{sourceRate.sourceRowRef}</strong><small>{sourceRate.sourceCode} · demo fixture, not a live ERP connection</small></div>
        </div>
        <div className="modal-cost">
          <Row label="Source as of">{formatDate(sourceRate.sourceAsOfDate)}</Row>
          <Row label="Producer">{sourceRate.rawProducer ?? "—"}{sourceRate.producer ? ` → ${sourceRate.producer.name}` : ""}</Row>
          <Row label="Grade">{sourceRate.rawGrade ?? "—"}{sourceRate.grade ? ` → ${sourceRate.grade.name}` : ""}</Row>
          <Row label="Location">{sourceRate.rawLocation ?? "—"}{sourceRate.market ? ` → ${sourceRate.market.name}` : ""}</Row>
          <Row label="Sector">{sourceRate.rawSector ?? "—"}{sourceRate.application ? ` · ${sourceRate.application}` : ""}</Row>
          <Row label="Resolution">{titleCase(sourceRate.resolutionStatus)}{sourceRate.resolutionReason ? ` · ${titleCase(sourceRate.resolutionReason)}` : ""}</Row>
          <Row label="Benchmark eligibility">{sourceRate.isBenchmarkEligible ? `Eligible · ${sourceRate.seriesCode}` : `Not eligible${sourceRate.eligibilityReason ? ` · ${titleCase(sourceRate.eligibilityReason)}` : ""}`}</Row>
          {sourceRate.isUnchanged && <Row label="Re-entry">Unchanged from previous as-of date</Row>}
          <Row label={`Value${sourceRate.priceBasis ? ` (${sourceRate.priceBasis}, ${sourceRate.taxBasis})` : ""}`}>{sourceRate.value ? `${formatMoney(sourceRate.value, 4)} / ${(sourceRate.unit ?? "").toLowerCase()}` : "—"}</Row>
        </div>
        {!selectable && <p><small>Only resolved, benchmark-eligible source rates can become a benchmark candidate.</small></p>}
        <ActionError error={error} />
      </ScrollBody>
      <div className="modal-actions">
        <Button variant="secondary" onClick={onClose}>Close</Button>
        <Button disabled={!selectable || busy} onClick={create}>Create benchmark candidate</Button>
      </div>
    </Modal>
  );
}

export function SeriesModal({ series, onClose, onOpenBenchmark }: { series: RateSeries; onClose: () => void; onOpenBenchmark: (benchmark: BenchmarkAdmin) => void }) {
  const timeline = useApiQuery(`timeline:${series.id}`, (signal) => getSeriesTimeline(series.id, signal));
  return (
    <Modal open title="Series history" onClose={onClose}>
      <ScrollBody>
        <div className="modal-product">
          <ProductVisual glyph={BENCHMARK_GLYPH} />
          <div><strong>{series.displayName}</strong><small>{series.code} · {series.priceBasis.label} · {series.taxBasis.label} · {series.currency} / {series.unit.label}</small></div>
        </div>
        {timeline.isLoading && !timeline.data && <p><small>Loading…</small></p>}
        {timeline.error ? <ActionError error={timeline.error} /> : null}
        {timeline.data && (
          <div className="modal-cost">
            {timeline.data.benchmarks.length === 0 && <span><small>No benchmarks yet</small></span>}
            {timeline.data.benchmarks.map((benchmark) => (
              <span key={benchmark.id} onClick={() => onOpenBenchmark(benchmark)} style={{ cursor: "pointer" }}>
                <small>{formatDate(benchmark.sourceAsOfDate)} · {titleCase(benchmark.method)}</small>
                <strong>{formatMoney(benchmark.value, 4)} <StatusBadge status={benchmark.status} /></strong>
              </span>
            ))}
          </div>
        )}
      </ScrollBody>
      <div className="modal-actions"><Button variant="secondary" onClick={onClose}>Close</Button></div>
    </Modal>
  );
}
