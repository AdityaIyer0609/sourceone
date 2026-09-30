import { Bell, ChevronDown, MapPin, Menu, Plus, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { paths } from "../../app/paths";
import { readSession } from "../../lib/api/auth";
import { onDeliveryPinChange, readDeliveryPin, saveDeliveryPin } from "../../lib/deliveryPin";
import { listApprovals, type OrderApproval } from "../../lib/api/approvals";
import { listNegotiations, type Negotiation } from "../../lib/api/negotiations";
import { listOrders, type Order } from "../../lib/api/orders";
import { useApiQuery } from "../../lib/api/useApiQuery";
import { Button, Input } from "../ui";

interface Notice {
  id: string;
  title: string;
  detail: string;
  to: string;
}

function noticesFor(negotiations: Negotiation[], orders: Order[], approvals: OrderApproval[]): Notice[] {
  const ordered = new Set(orders.map((order) => order.negotiation.id));
  const items: Notice[] = [];
  for (const item of negotiations) {
    const open = item.status === "draft" || item.status === "open" || item.status === "countered";
    if (open && item.awaiting === item.viewerRole) {
      items.push({
        id: item.id,
        title: item.product.name,
        detail: `${item.negotiationNumber} · Your turn to respond`,
        to: `${paths.negotiations}?id=${encodeURIComponent(item.id)}`,
      });
    }
    if (item.status === "accepted" && item.viewerRole === "buyer" && !ordered.has(item.id)) {
      items.push({
        id: `place-${item.id}`,
        title: `Place the order for ${item.product.name}`,
        detail: `${item.negotiationNumber} · Offer accepted`,
        to: `${paths.negotiations}?id=${encodeURIComponent(item.id)}`,
      });
    }
  }
  for (const order of orders) {
    if (order.viewerRole === "supplier" && order.status === "placed") {
      items.push({
        id: order.id,
        title: `Confirm ${order.orderNumber}`,
        detail: `${order.product.name} · Waiting for you`,
        to: `${paths.orders}?id=${encodeURIComponent(order.id)}`,
      });
    }
  }
  for (const approval of approvals) {
    if (approval.status === "pending") {
      items.push({
        id: approval.id,
        title: `Approve ${approval.negotiationNumber}`,
        detail: `${approval.productName} · ${approval.submittedBy} · material ${approval.amount.amount} ${approval.amount.currency}`,
        to: paths.approvals,
      });
    }
  }
  return items;
}

export function Topbar({ title, search, onMenu, onSearch }: { title: string; search: string; onMenu: () => void; onSearch: (value: string) => void }) {
  const navigate = useNavigate();
  const roles = readSession()?.user.roles ?? [];
  const buyer = roles.includes("buyer");
  const approver = roles.includes("approver");
  const trading = buyer || roles.includes("supplier");
  const [pin, setPin] = useState(readDeliveryPin);
  const [draft, setDraft] = useState(pin);
  const [panel, setPanel] = useState<"pin" | "notices" | null>(null);
  const negotiations = useApiQuery(trading ? "topbar-negotiations" : null, (signal) => listNegotiations(signal));
  const orders = useApiQuery(trading ? "topbar-orders" : null, (signal) => listOrders(signal));
  const approvals = useApiQuery(approver ? "topbar-approvals" : null, (signal) => listApprovals(signal));
  const notices = noticesFor(negotiations.data ?? [], orders.data ?? [], approvals.data ?? []);
  const pinOk = /^[1-9][0-9]{5}$/.test(draft);

  useEffect(() => onDeliveryPinChange(() => setPin(readDeliveryPin())), []);

  const open = (next: "pin" | "notices") => {
    setPanel((current) => (current === next ? null : next));
    if (next === "pin") setDraft(readDeliveryPin());
  };
  const go = (to: string) => {
    setPanel(null);
    navigate(to);
  };

  return (
    <header className="topbar">
      <Button variant="ghost" className="menu-button" onClick={onMenu} aria-label="Open navigation"><Menu size={20} /></Button>
      <div className="topbar__title"><small>PLENZA /</small><strong>{title}</strong></div>
      <label className="search-box">
        <Search size={18} />
        <Input aria-label="Search item master" placeholder="Search items, grades, standards or SKU…" value={search} onChange={(event) => onSearch(event.target.value)} />
        <kbd>⌘ K</kbd>
      </label>
      <div className="topbar-actions">
      <div className="topbar-menu">
        <Button variant="ghost" className="location" aria-expanded={panel === "pin"} onClick={() => open("pin")}><MapPin size={17} /> {pin ? <strong>{pin}</strong> : "Delivery PIN"} <ChevronDown size={14} /></Button>
        {panel === "pin" && (
          <div className="topbar-panel" role="dialog" aria-label="Set delivery PIN">
            <label>Delivery PIN<Input inputMode="numeric" aria-label="Delivery PIN" placeholder="6-digit PIN" value={draft} onChange={(event) => setDraft(event.target.value)} /></label>
            <p>Used as the delivery PIN for freight, purchase requests, and new orders.</p>
            <div className="topbar-panel__actions">
              <Button variant="secondary" onClick={() => { saveDeliveryPin(""); setDraft(""); setPin(""); }}>Clear</Button>
              <Button disabled={!pinOk} onClick={() => { saveDeliveryPin(draft); setPin(draft); setPanel(null); }}>Save</Button>
            </div>
          </div>
        )}
      </div>
      <div className="topbar-menu">
        <Button variant="ghost" className="icon-button notification" aria-label="Notifications" aria-expanded={panel === "notices"} onClick={() => open("notices")}>
          <Bell size={19} />
          {notices.length > 0 && <i />}
        </Button>
        {panel === "notices" && (
          <div className="topbar-panel topbar-panel--notices" role="dialog" aria-label="Notifications">
            {notices.length === 0 ? <p>Nothing needs your attention.</p> : notices.map((item) => (
              <button key={item.id} type="button" className="notice" onClick={() => go(item.to)}>
                <strong>{item.title}</strong>
                <small>{item.detail}</small>
              </button>
            ))}
          </div>
        )}
      </div>
      {buyer && <Button variant="dark" className="quick-order" onClick={() => navigate(paths.purchaseRequests)}><Plus size={17} /> New request</Button>}
      </div>
    </header>
  );
}
