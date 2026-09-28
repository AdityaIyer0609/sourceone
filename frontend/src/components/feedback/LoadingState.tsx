import { LoaderCircle } from "lucide-react";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state-panel" role="status" aria-live="polite">
      <span className="state-panel__icon"><LoaderCircle size={20} className="spin" /></span>
      <p>{label}</p>
    </div>
  );
}
