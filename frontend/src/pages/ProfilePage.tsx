import { useEffect, useState } from "react";
import { Badge, Button, Heading, Input } from "../components/ui";
import { clearSession, readSession } from "../lib/api/auth";
import { onDeliveryPinChange, readDeliveryPin, saveDeliveryPin } from "../lib/deliveryPin";
import { titleCase } from "../lib/pricingFormat";

function initials(name: string) {
  return name.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase() || "SO";
}

export function ProfilePage() {
  const session = readSession();
  const user = session?.user;
  const [pin, setPin] = useState(readDeliveryPin);
  const [draft, setDraft] = useState(readDeliveryPin);
  const pinOk = /^[1-9][0-9]{5}$/.test(draft);

  useEffect(() => onDeliveryPinChange(() => {
    const next = readDeliveryPin();
    setPin(next);
    setDraft(next);
  }), []);

  if (!user) {
    return (
      <div className="page">
        <div className="page-heading"><div><Heading level={1}>Profile</Heading><p>Sign in to see this account.</p></div></div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <small>ACCOUNT</small>
          <Heading level={1}>{user.fullName}</Heading>
          <p>{user.email}</p>
        </div>
      </div>
      <section className="section-block profile-card">
        <div className="avatar avatar--square profile-card__mark">{initials(user.fullName)}</div>
        <div className="profile-facts">
          <div><small>Name</small><strong>{user.fullName}</strong></div>
          <div><small>Email</small><strong>{user.email}</strong></div>
          <div><small>Organisation</small><strong>{user.organisation}</strong></div>
          <div><small>Roles</small><strong className="profile-roles">{user.roles.map((role) => <Badge key={role} tone="info">{titleCase(role)}</Badge>)}</strong></div>
        </div>
      </section>
      <section className="section-block profile-block">
        <Heading level={2}>Delivery PIN</Heading>
        <p>Used as the delivery PIN for freight, purchase requests, and new orders. It stays on this browser.</p>
        <div className="form-grid">
          <label>Delivery PIN<Input inputMode="numeric" aria-label="Delivery PIN" placeholder="6-digit PIN" value={draft} onChange={(event) => setDraft(event.target.value)} /></label>
        </div>
        <div className="modal-actions">
          <Button disabled={!pinOk || draft === pin} onClick={() => saveDeliveryPin(draft)}>Save PIN</Button>
          <Button variant="secondary" disabled={!pin && !draft} onClick={() => { saveDeliveryPin(""); setDraft(""); }}>Clear</Button>
        </div>
      </section>
      <section className="section-block profile-block">
        <Heading level={2}>Sign out</Heading>
        <p>Leaves Plenza on this browser. You can sign in again with the same email and password.</p>
        <Button variant="secondary" onClick={() => clearSession()}>Sign out</Button>
      </section>
    </div>
  );
}
