import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { BenchmarkSummary } from "../../lib/api/pricing";
import { formatDate, formatMoney, formatPercent, formatSignedMoney, movementDirection, sparklineValues } from "../../lib/pricingFormat";
import { Badge } from "../ui";
import { Sparkline } from "./Sparkline";

export function MarketTable({ benchmarks, compact = false, onSelect }: { benchmarks: BenchmarkSummary[]; compact?: boolean; onSelect?: (seriesCode: string) => void }) {
  return (
    <div className="market-table-wrap">
      <table className={`market-table${compact ? " market-table--compact" : ""}`}>
        <thead><tr><th>Material</th><th>Plenza benchmark</th><th>vs previous</th><th>7D movement</th><th>Market</th><th>As of</th></tr></thead>
        <tbody>
          {(compact ? benchmarks.slice(0, 4) : benchmarks).map((benchmark) => {
            const direction = movementDirection(benchmark);
            const down = direction === "down";
            const { current, movement } = benchmark;
            return (
              <tr key={benchmark.seriesCode} onClick={onSelect ? () => onSelect(benchmark.seriesCode) : undefined}>
                <td><strong>{benchmark.name}</strong><small>{benchmark.seriesCode}</small></td>
                <td>
                  <strong>{current ? formatMoney(current.value) : "Rate on request"}</strong>
                  <small>{current ? `/ ${benchmark.unit.label} · ${benchmark.priceBasis.label.toLowerCase()} · ${benchmark.taxBasis.label}` : "No current benchmark"}</small>
                  {benchmark.spread?.state === "ok" && benchmark.spread.minimum && benchmark.spread.maximum && <small>Spread {formatMoney(benchmark.spread.minimum)}–{formatMoney(benchmark.spread.maximum)}</small>}
                </td>
                <td>
                  {direction && movement.percent !== null ? (
                    <><span className={down ? "negative" : "positive"}>{down ? <ArrowDownRight size={14} /> : <ArrowUpRight size={14} />}{formatPercent(movement.percent)}</span><small>{movement.absolute ? formatSignedMoney(movement.absolute) : ""}</small></>
                  ) : <small>No previous benchmark</small>}
                </td>
                <td><Sparkline down={down} values={sparklineValues(benchmark.sparkline.points)} /></td>
                <td>{benchmark.market.label}</td>
                <td>
                  {current ? <small>{formatDate(current.freshness.asOfDate)}</small> : <small>—</small>}
                  {current?.freshness.state === "stale" && <Badge tone="warning">STALE</Badge>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
