import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { rateRows } from "../../mocks/data";
import { Sparkline } from "./Sparkline";

export function MarketTable({ compact = false }: { compact?: boolean }) {
  return (
    <div className="market-table-wrap">
      <table className="market-table">
        <thead><tr><th>Material</th><th>Live market rate</th><th>Today</th><th>7D movement</th><th>Market</th><th>Updated</th></tr></thead>
        <tbody>
          {rateRows.slice(0, compact ? 4 : 5).map((row) => {
            const down = row[4].startsWith("−");
            return (
              <tr key={row[1]}>
                <td><strong>{row[0]}</strong><small>{row[1]}</small></td>
                <td><strong>{row[2]}</strong><small>/ kg · ex-works</small></td>
                <td><span className={down ? "negative" : "positive"}>{down ? <ArrowDownRight size={14} /> : <ArrowUpRight size={14} />}{row[4]}</span><small>{row[3]}</small></td>
                <td><Sparkline down={down} /></td>
                <td>{row[5]}</td><td><small>{row[6]}</small></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
