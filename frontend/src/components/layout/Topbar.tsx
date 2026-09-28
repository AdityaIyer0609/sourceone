import { Bell, ChevronDown, MapPin, Menu, Plus, Search } from "lucide-react";
import { Button, Input } from "../ui";

export function Topbar({ title, search, onMenu, onSearch }: { title: string; search: string; onMenu: () => void; onSearch: (value: string) => void }) {
  return (
    <header className="topbar">
      <Button variant="ghost" className="menu-button" onClick={onMenu} aria-label="Open navigation"><Menu size={20} /></Button>
      <div className="topbar__title"><small>MERIDIAN /</small><strong>{title}</strong></div>
      <label className="search-box">
        <Search size={18} />
        <Input aria-label="Search item master" placeholder="Search items, grades, standards or SKU…" value={search} onChange={(event) => onSearch(event.target.value)} />
        <kbd>⌘ K</kbd>
      </label>
      <Button variant="ghost" className="location"><MapPin size={17} /> Deliver to <strong>390020</strong><ChevronDown size={14} /></Button>
      <Button variant="ghost" className="icon-button notification" aria-label="Notifications"><Bell size={19} /><i /></Button>
      <Button variant="dark" className="quick-order"><Plus size={17} /> New request</Button>
    </header>
  );
}
