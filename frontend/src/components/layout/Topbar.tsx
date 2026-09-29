import { Bell, ChevronDown, MapPin, Menu, Plus, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { paths } from "../../app/paths";
import { Button, Input } from "../ui";

export function Topbar({ title, search, onMenu, onSearch }: { title: string; search: string; onMenu: () => void; onSearch: (value: string) => void }) {
  const navigate = useNavigate();
  return (
    <header className="topbar">
      <Button variant="ghost" className="menu-button" onClick={onMenu} aria-label="Open navigation"><Menu size={20} /></Button>
      <div className="topbar__title"><small>PLENZA /</small><strong>{title}</strong></div>
      <label className="search-box">
        <Search size={18} />
        <Input aria-label="Search item master" placeholder="Search items, grades, standards or SKU…" value={search} onChange={(event) => onSearch(event.target.value)} />
        <kbd>⌘ K</kbd>
      </label>
      <Button variant="ghost" className="location" onClick={() => navigate(paths.freightCalculator)}><MapPin size={17} /> Delivery PIN <ChevronDown size={14} /></Button>
      <Button variant="ghost" className="icon-button" aria-label="Notifications" aria-disabled="true" title="Notifications are not available yet"><Bell size={19} /></Button>
      <Button variant="dark" className="quick-order" onClick={() => navigate(paths.purchaseRequests)}><Plus size={17} /> New request</Button>
    </header>
  );
}
