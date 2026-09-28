import { useState } from "react";
import { Outlet, ScrollRestoration, useLocation, useMatches, useNavigate, useSearchParams } from "react-router-dom";
import { paths, type RouteHandle } from "../../app/paths";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell() {
  const [mobileNav, setMobileNav] = useState(false);
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [searchParams] = useSearchParams();
  const matches = useMatches();

  const title = matches.map((match) => (match.handle as RouteHandle | undefined)?.title).filter(Boolean).at(-1) ?? "";
  const onCatalogue = pathname === paths.catalogue;
  const search = onCatalogue ? searchParams.get("q") ?? "" : "";

  const handleSearch = (value: string) => {
    if (!value && !onCatalogue) return;
    navigate(
      { pathname: paths.catalogue, search: value ? `?${new URLSearchParams({ q: value })}` : "" },
      { replace: onCatalogue },
    );
  };

  return (
    <div className="app-shell">
      <Sidebar open={mobileNav} onClose={() => setMobileNav(false)} />
      {mobileNav && <div className="nav-overlay" onClick={() => setMobileNav(false)} />}
      <main className="main-shell">
        <Topbar title={title} search={search} onMenu={() => setMobileNav(true)} onSearch={handleSearch} />
        <Outlet />
      </main>
      <ScrollRestoration />
    </div>
  );
}
