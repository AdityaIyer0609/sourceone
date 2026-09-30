import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { paths } from "../../app/paths";

export function OrgLink({ organisationId, children }: { organisationId: string; children: ReactNode }) {
  return <Link className="org-link" to={paths.supplier(organisationId)}>{children}</Link>;
}
