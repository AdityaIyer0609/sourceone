import { ArrowDownRight, ArrowUpRight } from "lucide-react";

export function Price({ value, uom, change }: { value: number; uom: string; change: number }) {
  const positive = change >= 0;
  return (
    <div className="price">
      <strong>₹{value.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong>
      <small> / {uom}</small>
      <span className={positive ? "positive" : "negative"}>
        {positive ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />} {Math.abs(change)}%
      </span>
    </div>
  );
}
