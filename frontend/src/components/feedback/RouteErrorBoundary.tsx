import { isRouteErrorResponse, useRouteError } from "react-router-dom";
import { NotFoundPage } from "../../pages/NotFoundPage";
import { ErrorState } from "./ErrorState";

export function RouteErrorBoundary() {
  const error = useRouteError();

  if (isRouteErrorResponse(error) && error.status === 404) return <NotFoundPage />;

  return (
    <div className="page">
      <ErrorState
        title="This page failed to load"
        message={isRouteErrorResponse(error) ? `${error.status} ${error.statusText}` : undefined}
        error={error}
        onRetry={() => window.location.reload()}
      />
    </div>
  );
}
