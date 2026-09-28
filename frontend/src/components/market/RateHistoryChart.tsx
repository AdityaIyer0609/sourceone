import { LineChart } from "lucide-react";
import type { BenchmarkHistory, HistoryRange } from "../../lib/api/pricing";
import { formatMoney, formatShortDay, titleCase } from "../../lib/pricingFormat";
import { EmptyState } from "../feedback/EmptyState";

const RANGE_DAYS: Record<HistoryRange, number> = { "1D": 1, "7D": 7, "1M": 30, "3M": 90, "1Y": 365 };
const WIDTH = 900;
const HEIGHT = 250;
const DAY_MS = 86_400_000;

interface Run {
  points: [x: number, y: number][];
}

/** Published benchmarks hold their value until the next one, so history is drawn as steps. */
function buildRuns(history: BenchmarkHistory, start: number, end: number, toX: (t: number) => number, toY: (v: number) => number): Run[] {
  const events = [...(history.carryIn ? [history.carryIn] : []), ...history.points]
    .map((point) => ({ at: Date.parse(point.at), value: Number(point.value) }))
    .sort((a, b) => a.at - b.at);
  const gaps = history.gaps.map((gap) => ({ start: Date.parse(gap.start), end: Date.parse(gap.end) }));
  const runs: Run[] = [];
  let run: Run | null = null;
  events.forEach((event, index) => {
    const from = Math.max(event.at, start);
    let until = index + 1 < events.length ? events[index + 1].at : end;
    const gap = gaps.find((g) => g.start >= from && g.start < until);
    if (gap) until = gap.start;
    const y = toY(event.value);
    if (run && run.points.at(-1)?.[0] === toX(from)) {
      run.points.push([toX(from), y]);
    } else {
      run = { points: [[toX(from), y]] };
      runs.push(run);
    }
    run.points.push([toX(until), y]);
    if (gap) run = null;
  });
  return runs;
}

export function RateHistoryChart({ history, range, now }: { history: BenchmarkHistory; range: HistoryRange; now: Date }) {
  const end = now.getTime();
  const start = end - RANGE_DAYS[range] * DAY_MS;
  const values = [...(history.carryIn ? [history.carryIn] : []), ...history.points].map((point) => Number(point.value));
  const money = (amount: string | number) => formatMoney({ amount: String(amount), currency: history.currency });
  const { stats } = history;
  const statCells: [string, string][] = [
    [`${range} high`, stats.high ? money(stats.high) : "—"],
    [`${range} low`, stats.low ? money(stats.low) : "—"],
    ["Average", stats.average ? money(stats.average) : "—"],
    ["Volatility", stats.volatility.state === "ok" && stats.volatility.level ? titleCase(stats.volatility.level) : "Insufficient data"],
    ["Data points", String(stats.pointCount)],
  ];

  if (!values.length) {
    return (
      <>
        <div className="chart-area"><EmptyState icon={LineChart} title="No benchmark history in this range" message="No published SourceOne benchmark was in effect during this period." /></div>
        <div className="chart-stats">{statCells.map(([a, b]) => <span key={a}><small>{a}</small><strong>{b}</strong></span>)}</div>
      </>
    );
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = max === min ? Math.max(max * 0.01, 0.01) : (max - min) * 0.15;
  const low = min - pad;
  const high = max + pad;
  const toX = (t: number) => ((Math.min(Math.max(t, start), end) - start) / (end - start)) * WIDTH;
  const toY = (v: number) => HEIGHT - 20 - ((v - low) / (high - low)) * (HEIGHT - 40);
  const runs = buildRuns(history, start, end, toX, toY);
  const line = runs.map((run) => run.points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ")).join(" ");
  const area = runs
    .map((run) => {
      const first = run.points[0];
      const last = run.points[run.points.length - 1];
      return `${run.points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ")} L${last[0].toFixed(1)} ${HEIGHT} L${first[0].toFixed(1)} ${HEIGHT}Z`;
    })
    .join(" ");
  const yTicks = [0, 1, 2, 3].map((i) => high - ((high - low) * i) / 3);
  const xTicks = Array.from({ length: 7 }, (_, i) => new Date(start + ((end - start) * i) / 6));

  return (
    <>
      <div className="chart-area">
        <div className="chart-y">{yTicks.map((tick) => <span key={tick}>{money(tick.toFixed(4))}</span>)}</div>
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="none" aria-label={`${range} SourceOne benchmark history`}><defs><linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="var(--accent)" stopOpacity=".18"/><stop offset="100%" stopColor="var(--accent)" stopOpacity="0"/></linearGradient></defs><path className="area-fill" d={area}/><path className="area-line" d={line}/></svg>
        <div className="chart-x">{xTicks.map((tick, i) => <span key={tick.getTime()}>{i === xTicks.length - 1 ? (range === "1D" ? "Now" : "Today") : formatShortDay(tick, range === "1D")}</span>)}</div>
      </div>
      <div className="chart-stats">{statCells.map(([a, b]) => <span key={a}><small>{a}</small><strong>{b}</strong></span>)}</div>
    </>
  );
}
