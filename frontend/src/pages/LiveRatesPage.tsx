import { Plus } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { AsyncContent } from "../components/feedback/AsyncContent";
import { MarketTable } from "../components/market/MarketTable";
import { RateHistoryChart } from "../components/market/RateHistoryChart";
import { Sparkline } from "../components/market/Sparkline";
import { Badge, Button, Heading } from "../components/ui";
import { getBenchmarkHistory, type HistoryRange } from "../lib/api/pricing";
import { useApiQuery } from "../lib/api/useApiQuery";
import { useBenchmarks } from "../lib/api/useBenchmarks";
import { formatClock, formatDate, formatMoney, formatPercent, formatSignedMoney, movementDirection, sparklineValues } from "../lib/pricingFormat";

const RANGES: HistoryRange[] = ["1D", "7D", "1M", "3M", "1Y"];

export function LiveRatesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: benchmarks = [], error, isLoading, reload, updatedAt } = useBenchmarks();
  const range = (RANGES as string[]).includes(searchParams.get("range") ?? "") ? (searchParams.get("range") as HistoryRange) : "7D";
  const selected =
    benchmarks.find((benchmark) => benchmark.seriesCode === searchParams.get("series")) ??
    benchmarks.find((benchmark) => benchmark.availability === "available") ??
    benchmarks[0];
  const history = useApiQuery(selected ? `history:${selected.seriesCode}:${range}` : null, (signal) => getBenchmarkHistory(selected!.seriesCode, range, signal));

  const select = (next: { series?: string; range?: HistoryRange }) => {
    const params = new URLSearchParams(searchParams);
    if (next.series) params.set("series", next.series);
    if (next.range) params.set("range", next.range);
    setSearchParams(params, { replace: true });
  };

  const liveCount = benchmarks.filter((benchmark) => benchmark.availability === "available").length;
  const selectedDirection = selected ? movementDirection(selected) : null;

  return (
    <div className="page">
      <div className="page-heading">
        <div><small>MARKET INTELLIGENCE</small><Heading level={1}>Live rate desk</Heading><p>Auditable benchmark pricing across primary industrial material markets.</p></div>
        <div className="market-open"><span className="live-dot" /><div><strong>{liveCount} of {benchmarks.length} benchmarks live</strong><small>{updatedAt ? `Last refresh ${formatClock(updatedAt)}` : "Refreshing…"}</small></div></div>
      </div>
      <AsyncContent isLoading={isLoading && !benchmarks.length} error={error} onRetry={reload} isEmpty={!benchmarks.length} emptyTitle="No benchmarks published yet" loadingLabel="Loading SourceOne benchmarks…">
        <div className="index-strip">
          {benchmarks.slice(0, 4).map((benchmark) => {
            const direction = movementDirection(benchmark);
            return (
              <div key={benchmark.seriesCode}>
                <small>{`${benchmark.grade.label} · ${benchmark.market.label}`.toUpperCase()}</small>
                <strong>{benchmark.current ? formatMoney(benchmark.current.value) : "On request"}</strong>
                <span className={direction === "down" ? "negative" : direction === "up" ? "positive" : ""}>
                  {direction && benchmark.movement.percent !== null ? formatPercent(benchmark.movement.percent) : benchmark.current ? "No previous" : "Rate on request"}
                </span>
                <Sparkline down={direction === "down"} values={sparklineValues(benchmark.sparkline.points)} />
              </div>
            );
          })}
        </div>
        {selected && (
          <section className="rate-chart-panel">
            <div className="section-title">
              <div>
                <Badge>{selected.category.toUpperCase()}</Badge> {selected.current?.freshness.state === "stale" && <Badge tone="warning">STALE</Badge>}
                <Heading level={2}>{selected.name}</Heading>
                <p>
                  {selected.current ? (
                    <>
                      {formatMoney(selected.current.value)} / {selected.unit.label} · as of {formatDate(selected.current.freshness.asOfDate)}{" "}
                      {selectedDirection && selected.movement.absolute && <span className={selectedDirection === "down" ? "negative" : "positive"}>{formatSignedMoney(selected.movement.absolute)} vs previous</span>}
                    </>
                  ) : "Rate on request"}
                </p>
              </div>
              <div className="range-switch">{RANGES.map((value) => <Button variant="ghost" className={value === range ? "is-active" : ""} key={value} onClick={() => select({ range: value })}>{value}</Button>)}</div>
            </div>
            <AsyncContent isLoading={history.isLoading && !history.data} error={history.error} onRetry={history.reload} loadingLabel="Loading benchmark history…">
              {history.data && <RateHistoryChart history={history.data} range={range} now={history.updatedAt ?? new Date()} />}
            </AsyncContent>
          </section>
        )}
        <section className="section-block"><div className="section-title"><div><small>WATCHLIST</small><Heading level={2}>Tracked benchmarks</Heading></div><Button variant="secondary" aria-disabled="true" title="Watchlist editing is not available yet"><Plus size={16} /> Add material</Button></div><MarketTable benchmarks={benchmarks} onSelect={(series) => select({ series })} /></section>
      </AsyncContent>
    </div>
  );
}
