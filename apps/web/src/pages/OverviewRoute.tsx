// /overview (UI v2, docs/design/v2/01-overview.png) for owners, admins, managers and reviewers: the period's numbers
// and coaching table (features/overview), what needs a decision (GET /v1/inbox), what is being processed right now
// and the newest recordings with who spoke when. Everything comes from the API, for what the signed-in person may
// see.

import { useState } from "react";
import { useOutletContext } from "react-router-dom";

import { useInbox, useOverview } from "../api/hooks";
import type { Me } from "../api/types";
import { capitalise } from "../app/format";
import { RESOLVERS } from "../app/nav";
import { Button, EmptyState, Icon, Panel, type ConversationType } from "../design";
import { InboxList } from "../features/inbox/InboxList";
import { ALL_UNITS } from "../features/overview/metrics";
import { OverviewPage } from "../features/overview/OverviewPage";
import { useOpen } from "../app/useOpen";
import { Processing, Recent } from "../features/overview/panels";
import { COMPARE, presetRange, toQuery, type DayRange, type RangePreset } from "../features/overview/range";

const DECISIONS_SHOWN = 4;

function Decisions({ me }: { me: Me }) {
  const inbox = useInbox();
  const open = useOpen();
  const items = inbox.data?.items ?? [];
  const resolver = RESOLVERS.includes(me.user.role);
  return (
    <Panel
      flush
      title="Needs your decision"
      actions={
        resolver && (
          <a href="/reviews" onClick={(e) => open(e, "/reviews")} className="text-sm font-semibold no-underline">
            Open reviews
          </a>
        )
      }
    >
      {inbox.isError ? (
        <p className="m-0 px-5 py-4 text-sm text-muted">We couldn't load this. Please try again in a moment.</p>
      ) : items.length === 0 ? (
        <p className="m-0 px-5 py-4 text-sm text-muted">{inbox.isSuccess ? "Nothing is waiting for you." : " "}</p>
      ) : (
        <>
          <InboxList items={items.slice(0, DECISIONS_SHOWN)} me={me} />
          {items.length > DECISIONS_SHOWN && (
            <p className="m-0 border-t border-line-subtle px-5 py-3 text-sm text-muted">
              And {items.length - DECISIONS_SHOWN} more under the bell at the top.
            </p>
          )}
        </>
      )}
    </Panel>
  );
}

export function OverviewRoute() {
  const me = useOutletContext<Me>();
  const [preset, setPreset] = useState<RangePreset>("7d");
  const [range, setRange] = useState<DayRange>(() => presetRange("7d", new Date()));
  const [unit, setUnit] = useState(ALL_UNITS);
  const overview = useOverview(toQuery(range), unit === ALL_UNITS ? null : unit);
  const inbox = useInbox();
  const typeNames = Object.fromEntries(
    (["teaching", "reception", "counselling", "meeting", "sales", "support"] as ConversationType[]).map((t) => [
      t,
      capitalise(t),
    ]),
  ) as Record<ConversationType, string>;

  if (overview.isError) {
    return (
      <Panel>
        <EmptyState
          icon={<Icon name="alert" size={26} />}
          title="We couldn't load the overview"
          description="Please try again in a moment."
          action={<Button onClick={() => void overview.refetch()}>Try again</Button>}
        />
      </Panel>
    );
  }
  return (
    <OverviewPage
      stats={overview.data}
      name={me.user.name.split(" ")[0] ?? me.user.name}
      preset={preset}
      range={range}
      onRangeChange={(p, r) => {
        setPreset(p);
        setRange(r);
      }}
      compare={COMPARE[preset]}
      unit={unit}
      onUnitChange={setUnit}
      typeNames={typeNames}
      labels={me.tenant.labels}
      enabledTypes={me.tenant.enabled_types as ConversationType[]}
      waiting={inbox.data?.items.length}
      decisions={<Decisions me={me} />}
      processing={overview.data && <Processing stats={overview.data} typeNames={typeNames} />}
      recent={<Recent me={me} />}
    />
  );
}
