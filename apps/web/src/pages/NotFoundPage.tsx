// Any address inside the app that is not a page: a friendly way back instead of a dead end.

import { useNavigate, useOutletContext } from "react-router-dom";

import type { Me } from "../api/types";
import { Button, EmptyState, Icon } from "../design";

export function NotFoundPage() {
  const me = useOutletContext<Me>();
  const navigate = useNavigate();
  return (
    <div className="rounded-panel border border-line bg-surface">
      <EmptyState
        className="py-16"
        icon={<Icon name="search" size={26} />}
        title="We couldn't find that page"
        description="The link may be old, or the page may have moved."
        action={
          <Button onClick={() => navigate("/recordings")}>
            Go to {me.tenant.labels.recording_plural.toLowerCase()}
          </Button>
        }
      />
    </div>
  );
}
