import "@fontsource/instrument-sans/400.css";
import "@fontsource/instrument-sans/500.css";
import "@fontsource/instrument-sans/600.css";
import "@fontsource/instrument-sans/700.css";
import "./index.css";

import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";

import { AuthProvider, ProtectedRoute, readAuthConfig } from "./auth";
import OverviewSpike from "./spike/OverviewSpike";

const container = document.getElementById("root");
if (!container) throw new Error("#root element missing from index.html");
const root = createRoot(container);
const render = (page: ReactNode) => root.render(<StrictMode>{page}</StrictMode>);

// The demos (/dev/components, /dev/transcript, /dev/report, /dev/reviews, /dev/overview) are dev only. In production builds `import.meta.env.DEV` is the
// constant false, so these branches and their dynamic imports are removed and the demos are never bundled.
// React Router replaces this in P6.2.
if (import.meta.env.DEV && location.pathname === "/dev/components") {
  void import("./dev/ComponentsDemo").then(({ default: ComponentsDemo }) => render(<ComponentsDemo />));
} else if (import.meta.env.DEV && location.pathname === "/dev/transcript") {
  void import("./dev/TranscriptDemo").then(({ default: TranscriptDemo }) => render(<TranscriptDemo />));
} else if (import.meta.env.DEV && location.pathname === "/dev/report") {
  void import("./dev/ReportDemo").then(({ default: ReportDemo }) => render(<ReportDemo />));
} else if (import.meta.env.DEV && location.pathname === "/dev/reviews") {
  void import("./dev/ReviewsDemo").then(({ default: ReviewsDemo }) => render(<ReviewsDemo />));
} else if (import.meta.env.DEV && location.pathname === "/dev/overview") {
  void import("./dev/OverviewDemo").then(({ default: OverviewDemo }) => render(<OverviewDemo />));
} else {
  // The demos above use mock data and stay open in development; the app itself needs a signed-in person.
  render(
    <AuthProvider config={readAuthConfig(import.meta.env)}>
      <ProtectedRoute>
        <OverviewSpike />
      </ProtectedRoute>
    </AuthProvider>,
  );
}
