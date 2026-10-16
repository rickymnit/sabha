// Demo of the overview numbers (P6.4b), served at /dev/overview in development only (see main.tsx). Mock data; the
// real page reads GET /v1/overview?from&to with the range from toQuery().

import { useState } from "react";

import { emptyOverview, mockLabels, mockOverview, mockTypeNames } from "../features/overview/mock";
import { OverviewPage } from "../features/overview/OverviewPage";
import { presetRange, type DayRange, type RangePreset } from "../features/overview/range";

export default function OverviewDemo() {
  const [preset, setPreset] = useState<RangePreset>("7d");
  const [range, setRange] = useState<DayRange>(() => presetRange("7d", new Date()));
  // ?empty shows the page for a period with nothing analysed.
  const stats = new URLSearchParams(location.search).has("empty") ? emptyOverview() : mockOverview();
  return (
    <main className="mx-auto max-w-[1200px] p-6">
      <OverviewPage
        stats={stats}
        scopeLabel="All campuses"
        preset={preset}
        range={range}
        onRangeChange={(p, r) => {
          setPreset(p);
          setRange(r);
        }}
        typeNames={mockTypeNames}
        labels={mockLabels}
        rubricHref={(id) => `/rubrics/${id}`}
      />
    </main>
  );
}
