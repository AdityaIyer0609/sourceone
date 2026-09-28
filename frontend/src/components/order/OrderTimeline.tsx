import { Check } from "lucide-react";
import type { TrackingStep } from "../../lib/api/orders";
import { formatDateTime } from "../../lib/pricingFormat";

export function OrderTimeline({ steps }: { steps: TrackingStep[] }) {
  return (
    <div className="timeline">
      {steps.map((step) => (
        <div className={step.state === "pending" ? "" : "done"} key={step.status} aria-current={step.state === "current" ? "step" : undefined}>
          <i>{step.state === "completed" ? <Check size={12}/> : null}</i>
          <span>
            <strong>{step.label}</strong>
            <small>{step.at ? `${formatDateTime(step.at)}${step.changedBy ? ` · ${step.changedBy}` : ""}` : "Pending"}</small>
            {step.note ? <small>{step.note}</small> : null}
          </span>
        </div>
      ))}
    </div>
  );
}
