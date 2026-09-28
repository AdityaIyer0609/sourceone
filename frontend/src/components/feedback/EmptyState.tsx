import { Inbox, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Heading } from "../ui";

export function EmptyState({
  icon: Icon = Inbox,
  title,
  message,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  message?: string;
  action?: ReactNode;
}) {
  return (
    <div className="state-panel">
      <span className="state-panel__icon"><Icon size={20} /></span>
      <Heading level={2}>{title}</Heading>
      {message && <p>{message}</p>}
      {action}
    </div>
  );
}
