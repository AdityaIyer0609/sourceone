import { ChevronDown, ChevronRight, Settings2, Sparkles, X } from "lucide-react";
import { NavLink } from "react-router-dom";
import { commerceNav, controlCentreNav, type NavItem } from "../../app/navigation";
import { Button } from "../ui";
import { Logo } from "./Logo";

function SidebarLink({ item, onNavigate }: { item: NavItem; onNavigate: () => void }) {
  const { label, to, icon: Icon, badge } = item;
  return (
    <NavLink to={to} end className={({ isActive }) => `button button--ghost nav-item ${isActive ? "is-active" : ""}`} onClick={onNavigate}>
      <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
      {badge !== undefined && <em>{badge}</em>}
    </NavLink>
  );
}

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <aside className={`sidebar ${open ? "is-open" : ""}`}>
      <div className="sidebar__top">
        <Logo />
        <Button variant="ghost" className="mobile-close" onClick={onClose} aria-label="Close navigation"><X size={20} /></Button>
      </div>
      <div className="workspace-switcher">
        <div className="avatar avatar--square">AI</div>
        <div><strong>Ardent Industries</strong><small>Enterprise buyer</small></div>
        <ChevronDown size={15} />
      </div>
      <nav className="nav-list" aria-label="Primary navigation">
        <small className="nav-kicker">COMMERCE</small>
        {commerceNav.map((item) => <SidebarLink key={item.to} item={item} onNavigate={onClose} />)}
        <small className="nav-kicker nav-kicker--spaced">CONTROL CENTRE</small>
        {controlCentreNav.map((item) => <SidebarLink key={item.to} item={item} onNavigate={onClose} />)}
      </nav>
      <div className="sidebar__support">
        <div className="support-icon"><Sparkles size={18} /></div>
        <div><strong>Priority procurement desk</strong><small>Response in under 15 minutes</small></div>
        <ChevronRight size={16} />
      </div>
      <div className="user-strip">
        <div className="avatar">RM</div>
        <div><strong>Rohan Mehta</strong><small>Procurement lead</small></div>
        <Settings2 size={17} />
      </div>
    </aside>
  );
}
