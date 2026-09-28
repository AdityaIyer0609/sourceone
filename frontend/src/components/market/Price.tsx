import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { Money } from "../../lib/api/pricing";
import { formatMoney } from "../../lib/pricingFormat";

export function Price({ value, uom, change }: { value: Money | null; uom: string; change?: string | null }) {
  if (!value) {
    return (
      <div className="price">
        <strong>Rate on request</strong>
      </div>
    );
  }
  const changeValue = change === null || change === undefined ? null : Number(change);
  const positive = changeValue !== null && changeValue >= 0;
  return (
    <div className="price">
      <strong>{formatMoney(value)}</strong>
      <small> / {uom}</small>
      {changeValue !== null && (
        <span className={positive ? "positive" : "negative"}>
          {positive ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />} {Math.abs(changeValue).toFixed(2)}%
        </span>
      )}
    </div>
  );
}
