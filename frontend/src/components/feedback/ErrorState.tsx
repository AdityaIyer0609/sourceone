import { RefreshCw, TriangleAlert } from "lucide-react";
import { getErrorMessage, getErrorTitle } from "../../lib/api/client";
import { Button, Heading } from "../ui";

export function ErrorState({
  title,
  error,
  message,
  onRetry,
}: {
  title?: string;
  error?: unknown;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <span className="state-panel__icon"><TriangleAlert size={20} /></span>
      <Heading level={2}>{title ?? getErrorTitle(error)}</Heading>
      <p>{message ?? getErrorMessage(error)}</p>
      {onRetry && <Button variant="secondary" onClick={onRetry}><RefreshCw size={16} /> Try again</Button>}
    </div>
  );
}
