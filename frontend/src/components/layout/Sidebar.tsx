import { Settings2, Sparkles, X } from "lucide-react";
import { NavLink } from "react-router-dom";
import { commerceNav, controlCentreNav, type NavItem } from "../../app/navigation";
import { paths } from "../../app/paths";
import { clearSession, readSession } from "../../lib/api/auth";
import { listNegotiations } from "../../lib/api/negotiations";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { Button } from "../ui";
import { Logo } from "./Logo";

const OPEN_NEGOTIATION = new Set(["draft", "open", "countered"]);

function SidebarLink({ item, onNavigate }: { item: NavItem; onNavigate: () => void }) {
  const { label, to, icon: Icon, badge } = item;
  return (
    <NavLink to={to} end className={({ isActive }) => `button button--ghost nav-item ${isActive ? "is-active" : ""}`} onClick={onNavigate}>
      <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
      {badge !== undefined && <em>{badge}</em>}
    </NavLink>
  );
}

function initials(name: string) {
  return name.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase() || "SO";
}

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const session = readSession();
  const name = session?.user.fullName ?? "Signed in";
  const role = session?.user.roles[0]?.replace(/_/g, " ") ?? "Account";
  const negotiations = useApiQuery("nav-negotiations", (signal) => listNegotiations(signal));
  const openNegotiations = (negotiations.data ?? []).filter((item) => OPEN_NEGOTIATION.has(item.status)).length;
  const nav = commerceNav.map((item) => item.to === paths.negotiations && openNegotiations > 0 ? { ...item, badge: openNegotiations } : item);
  return (
    <aside className={`sidebar ${open ? "is-open" : ""}`}>
      <div className="sidebar__top">
        <Logo />
        <Button variant="ghost" className="mobile-close" onClick={onClose} aria-label="Close navigation"><X size={20} /></Button>
      </div>
      <div className="workspace-switcher">
        <div className="avatar avatar--square">{initials(session?.user.organisation ?? "SO")}</div>
        <div><strong>{session?.user.organisation ?? "Plenza"}</strong><small>{role}</small></div>
      </div>
      <nav className="nav-list" aria-label="Primary navigation">
        <small className="nav-kicker">COMMERCE</small>
        {nav.map((item) => <SidebarLink key={item.to} item={item} onNavigate={onClose} />)}
        <small className="nav-kicker nav-kicker--spaced">CONTROL CENTRE</small>
        {controlCentreNav.map((item) => <SidebarLink key={item.to} item={item} onNavigate={onClose} />)}
      </nav>
      <div className="sidebar__support">
        <div className="support-icon"><Sparkles size={18} /></div>
        <div><strong>Procurement desk</strong><small>No live desk is connected</small></div>
      </div>
      <div className="user-strip">
        <div className="avatar">{initials(name)}</div>
        <div><strong>{name}</strong><small>{session?.user.email}</small></div>
        <Button variant="ghost" className="icon-button" aria-label="Sign out" onClick={() => clearSession()}><Settings2 size={17} /></Button>
      </div>
    </aside>
  );
}
