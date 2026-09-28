import { ArrowRight, Compass } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { paths } from "../app/paths";
import { EmptyState } from "../components/feedback/EmptyState";
import { Button } from "../components/ui";

export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <div className="page">
      <EmptyState
        icon={Compass}
        title="Page not found"
        message="The page you are looking for does not exist or has moved."
        action={<Button onClick={() => navigate(paths.marketplace)}>Back to marketplace <ArrowRight size={16} /></Button>}
      />
    </div>
  );
}
