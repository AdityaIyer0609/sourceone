import { useState } from "react";
import { Button, Heading, Input } from "../components/ui";
import { getErrorMessage } from "../lib/api/client";
import { login, saveSession, type Session } from "../lib/api/auth";

const ACCOUNTS = [
  ["admin@demo.sourceone", "Platform admin"],
  ["pricing@demo.sourceone", "Pricing admin"],
  ["buyer@demo.sourceone", "Buyer"],
  ["supplier@demo.sourceone", "Supplier"],
] as const;

const DEVELOPMENT_PASSWORD = "SourceOne-demo";

export function LoginPage({ onSuccess }: { onSuccess: (session: Session) => void }) {
  const [email, setEmail] = useState<string>(ACCOUNTS[2][0]);
  const [password, setPassword] = useState(DEVELOPMENT_PASSWORD);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await login(email, password);
      const session = { accessToken: result.accessToken, user: result.user };
      saveSession(session);
      onSuccess(session);
    } catch (cause) {
      setError(getErrorMessage(cause));
      setBusy(false);
    }
  };
  return (
    <div className="sign-in">
      <section className="section-block sign-in__card">
        <div className="sign-in__head">
          <Heading level={1} className="sign-in__title">Sign in</Heading>
        </div>
        <div className="sign-in__body">
        <p className="sign-in__note">Choose a development account. These passwords are for local demonstration only.</p>
        <div className="sign-in__accounts">
          {ACCOUNTS.map(([account, label]) => (
            <Button key={account} variant="ghost" className={`filter-chip${email === account ? " is-active" : ""}`} onClick={() => { setEmail(account); setPassword(DEVELOPMENT_PASSWORD); }}>{label}</Button>
          ))}
        </div>
        <div className="sign-in__fields">
          <label>Email<Input aria-label="Email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          <label>Password<Input aria-label="Password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        </div>
        {error && <p className="negative">{error}</p>}
        <div className="sign-in__actions"><Button disabled={busy || !email || !password} onClick={() => void submit()}>{busy ? "Signing in…" : "Sign in"}</Button></div>
        </div>
      </section>
    </div>
  );
}
