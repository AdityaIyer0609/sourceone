import { ChevronRight, Filter, Search } from "lucide-react";
import { useState, type ReactNode } from "react";
import { AsyncContent } from "../../components/feedback/AsyncContent";
import { Badge, Button, Input } from "../../components/ui";
import {
  listAdminBenchmarks,
  listAuditEvents,
  listRateSeries,
  listRateSources,
  listSourceRates,
  type BenchmarkAdmin,
  type RateSeries,
  type SourceRate,
} from "../../lib/api/pricing";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { formatDate, formatDateTime, formatMoney, titleCase } from "../../lib/pricingFormat";
import { BenchmarkModal, SeriesModal, SourceRateModal, StatusBadge } from "./RateManagementModals";

type View = "queue" | "benchmarks" | "series" | "sourceRates" | "sources" | "audit";

const VIEWS: [View, string][] = [
  ["queue", "Review queue"],
  ["benchmarks", "Benchmarks"],
  ["series", "Rate series"],
  ["sourceRates", "Source rates"],
  ["sources", "Rate sources"],
  ["audit", "Audit"],
];

type Selection =
  | { kind: "benchmark"; benchmark: BenchmarkAdmin }
  | { kind: "series"; series: RateSeries }
  | { kind: "sourceRate"; sourceRate: SourceRate }
  | null;

async function loadWorkspace(signal: AbortSignal) {
  const [sources, series, benchmarks, sourceRates, audit] = await Promise.all([
    listRateSources(signal),
    listRateSeries(signal),
    listAdminBenchmarks({ limit: 200 }, signal),
    listSourceRates({ limit: 200 }, signal),
    listAuditEvents({ limit: 100 }, signal),
  ]);
  return { sources, series, benchmarks, sourceRates, audit };
}

const matches = (search: string, ...values: (string | null | undefined)[]) =>
  !search || values.filter(Boolean).join(" ").toLowerCase().includes(search.toLowerCase());

function seriesState(series: RateSeries) {
  if (series.availability === "rate_on_request") return <Badge tone="negative">RATE ON REQUEST</Badge>;
  return series.freshnessState === "stale" ? <Badge tone="warning">STALE</Badge> : <Badge tone="positive">FRESH</Badge>;
}

export function RateManagementWorkspace() {
  const [view, setView] = useState<View>("queue");
  const [search, setSearch] = useState("");
  const [selection, setSelection] = useState<Selection>(null);
  const workspace = useApiQuery("rate-management", loadWorkspace);
  const data = workspace.data;

  const seriesById = new Map(data?.series.map((series) => [series.id, series]));
  const benchmarkSeries = new Map(data?.benchmarks.map((benchmark) => [benchmark.id, benchmark.seriesCode]));
  const pending = data?.benchmarks.filter((benchmark) => benchmark.status === "draft" || benchmark.status === "submitted") ?? [];
  const submitted = pending.filter((benchmark) => benchmark.status === "submitted").length;
  const live = data?.series.filter((series) => series.availability === "available") ?? [];
  const stale = live.filter((series) => series.freshnessState === "stale").length;
  const unresolved = data?.sourceRates.filter((rate) => rate.resolutionStatus !== "resolved").length ?? 0;
  const ineligible = data?.sourceRates.filter((rate) => rate.resolutionStatus === "resolved" && !rate.isBenchmarkEligible).length ?? 0;

  const benchmarkRows = (rows: BenchmarkAdmin[]) =>
    rows
      .filter((b) => matches(search, b.seriesCode, b.status, b.method, b.primarySourceCode, b.createdBy))
      .map((b) => (
        <tr key={b.id} onClick={() => setSelection({ kind: "benchmark", benchmark: b })}>
          <td><strong>{b.seriesCode}</strong><small>{b.id.slice(0, 8)}</small></td>
          <td><strong>{seriesById.get(b.seriesId)?.displayName ?? b.seriesCode}</strong><small>{titleCase(b.method)} · {b.origin === "system_suggestion" ? "System suggestion" : "Human entry"}{b.fourEyesRequired ? " · Four-eyes" : ""}</small></td>
          <td><strong>{formatMoney(b.value, 4)}</strong><small>/ {b.unit.toLowerCase()} · {b.value.currency}</small></td>
          <td><strong>{formatDate(b.sourceAsOfDate)}</strong><small>Effective {formatDateTime(b.effectiveFrom)}</small></td>
          <td><StatusBadge status={b.status} /></td>
          <td><small>{b.publishedBy ?? b.submittedBy ?? b.createdBy ?? "system"}</small><small>{formatDateTime(b.publishedAt ?? b.submittedAt ?? b.createdAt)}</small></td>
          <td><ChevronRight size={16} /></td>
        </tr>
      ));

  const tables: Record<View, () => [string[], ReactNode[]]> = {
    queue: () => [["Series", "Material / method", "Value", "As of / effective", "Status", "Updated", ""], benchmarkRows(pending)],
    benchmarks: () => [["Series", "Material / method", "Value", "As of / effective", "Status", "Updated", ""], benchmarkRows(data?.benchmarks ?? [])],
    series: () => [
      ["Series", "Grade / market", "Currency / unit", "Price basis", "Current", "Benchmark", ""],
      (data?.series ?? []).filter((s) => matches(search, s.code, s.displayName, s.market.name, s.currency)).map((s) => (
        <tr key={s.id} onClick={() => setSelection({ kind: "series", series: s })}>
          <td><strong>{s.code}</strong></td>
          <td><strong>{s.displayName}</strong><small>{s.grade.name} · {s.market.name}</small></td>
          <td><strong>{s.currency}</strong><small>/ {s.unit.label}</small></td>
          <td><strong>{s.priceBasis.label}</strong><small>{s.taxBasis.label}</small></td>
          <td>{seriesState(s)}</td>
          <td><small>{s.currentBenchmarkId ? s.currentBenchmarkId.slice(0, 8) : "—"}</small></td>
          <td><ChevronRight size={16} /></td>
        </tr>
      )),
    ],
    sourceRates: () => [
      ["Source row", "Producer / grade", "Sector", "Value", "Resolution", "As of", ""],
      (data?.sourceRates ?? []).filter((r) => matches(search, r.sourceRowRef, r.rawProducer, r.rawGrade, r.rawLocation, r.sector, r.seriesCode, r.resolutionReason)).map((r) => (
        <tr key={r.id} onClick={() => setSelection({ kind: "sourceRate", sourceRate: r })}>
          <td><strong>{r.sourceRowRef}</strong><small>{r.sourceCode}</small></td>
          <td><strong>{r.rawProducer ?? "—"} · {r.rawGrade ?? "—"}</strong><small>{r.rawLocation ?? "—"}</small></td>
          <td><strong>{r.sector ? titleCase(r.sector.toLowerCase()) : "—"}</strong><small>{r.isBenchmarkEligible ? `Eligible · ${r.seriesCode}` : titleCase(r.eligibilityReason ?? "not eligible")}</small></td>
          <td><strong>{r.value ? formatMoney(r.value, 4) : "—"}</strong><small>{r.unit ? `/ ${r.unit.toLowerCase()}` : ""}{r.isUnchanged ? " · unchanged" : ""}</small></td>
          <td><Badge tone={r.resolutionStatus === "resolved" ? (r.isBenchmarkEligible ? "positive" : "neutral") : "warning"}>{r.resolutionStatus === "resolved" ? (r.isBenchmarkEligible ? "ELIGIBLE" : "NOT ELIGIBLE") : titleCase(r.resolutionReason ?? r.resolutionStatus).toUpperCase()}</Badge></td>
          <td><small>{formatDate(r.sourceAsOfDate)}</small></td>
          <td><ChevronRight size={16} /></td>
        </tr>
      )),
    ],
    sources: () => [
      ["Code", "Name", "Type", "Staleness", "Status", "Priority", ""],
      (data?.sources ?? []).filter((s) => matches(search, s.code, s.name, s.sourceType)).map((s) => (
        <tr key={s.id}>
          <td><strong>{s.code}</strong><small>Profile v{s.profileVersion}</small></td>
          <td><strong>{s.name}</strong><small>{titleCase(s.publishingPolicy)}</small></td>
          <td>{titleCase(s.sourceType)}</td>
          <td><strong>{s.stalenessDays} days</strong></td>
          <td><Badge tone={s.isActive ? "positive" : "neutral"}>{s.isActive ? "ACTIVE" : "INACTIVE"}</Badge></td>
          <td><small>{s.priority}</small></td>
          <td />
        </tr>
      )),
    ],
    audit: () => [
      ["When", "Action", "Series", "Actor", "Status change", "Reason", ""],
      (data?.audit ?? []).filter((e) => matches(search, e.action, e.actor, e.reason, benchmarkSeries.get(e.entityId))).map((e) => (
        <tr key={e.id}>
          <td><small>{formatDateTime(e.occurredAt)}</small></td>
          <td><strong>{titleCase(e.action)}</strong></td>
          <td><strong>{benchmarkSeries.get(e.entityId) ?? e.entityId.slice(0, 8)}</strong><small>{titleCase(e.entityType)}</small></td>
          <td><small>{e.actor ?? "system"}</small></td>
          <td>{e.fromStatus || e.toStatus ? <small>{e.fromStatus ?? "—"} → {e.toStatus ?? "—"}</small> : <small>—</small>}</td>
          <td><small>{e.reason ?? "—"}</small></td>
          <td />
        </tr>
      )),
    ],
  };
  const [headers, rows] = tables[view]();
  const empty = rows.length === 0;

  return (
    <AsyncContent isLoading={workspace.isLoading && !data} error={workspace.error} onRetry={workspace.reload} loadingLabel="Loading rate management…">
      <div className="metric-row">
        {[
          ["PENDING REVIEW", String(pending.length), `${submitted} submitted · ${pending.length - submitted} draft`],
          ["LIVE BENCHMARKS", `${live.length}/${data?.series.length ?? 0}`, `${stale} stale · ${(data?.series.length ?? 0) - live.length} on request`],
          ["SOURCE RATES", String(data?.sourceRates.length ?? 0), `${unresolved} unresolved · ${ineligible} not eligible`],
          ["RATE SOURCES", String(data?.sources.filter((s) => s.isActive).length ?? 0), (data?.sources ?? []).map((s) => `${s.code} ${s.stalenessDays}d`).join(" · ")],
        ].map(([a, b, c]) => <div key={a}><small>{a}</small><strong>{b}</strong><span>{c}</span></div>)}
      </div>
      <section className="section-block data-section">
        <div className="tabs">{VIEWS.map(([key, label]) => <Button key={key} variant="ghost" className={view === key ? "is-active" : ""} onClick={() => setView(key)}>{label}</Button>)}</div>
        <div className="data-toolbar"><label className="search-box search-box--small"><Search size={17}/><Input placeholder="Search rate management…" value={search} onChange={(event) => setSearch(event.target.value)}/></label><div><Button variant="secondary" aria-disabled="true" title="Advanced filters are not available yet"><Filter size={16}/> Filter</Button><Button variant="secondary" aria-disabled="true" title="Export is not available yet">Export</Button></div></div>
        {empty ? (
          <div className="state-panel"><p>{view === "queue" ? "No drafts or submitted benchmarks are waiting for review." : "No matching records."}</p></div>
        ) : (
          <div className="market-table-wrap"><table className="market-table"><thead><tr>{headers.map((header, index) => <th key={`${header}-${index}`}>{header}</th>)}</tr></thead><tbody>{rows}</tbody></table></div>
        )}
      </section>
      {selection?.kind === "benchmark" && <BenchmarkModal key={selection.benchmark.id} benchmark={selection.benchmark} onClose={() => setSelection(null)} onChanged={workspace.reload} />}
      {selection?.kind === "sourceRate" && <SourceRateModal sourceRate={selection.sourceRate} onClose={() => setSelection(null)} onCreated={(benchmark) => { workspace.reload(); setSelection({ kind: "benchmark", benchmark }); }} />}
      {selection?.kind === "series" && <SeriesModal series={selection.series} onClose={() => setSelection(null)} onOpenBenchmark={(benchmark) => setSelection({ kind: "benchmark", benchmark })} />}
    </AsyncContent>
  );
}
