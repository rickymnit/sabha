import "@fontsource/instrument-sans/400.css";
import "@fontsource/instrument-sans/500.css";
import "@fontsource/instrument-sans/600.css";
import "@fontsource/instrument-sans/700.css";
import "./index.css";

import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";

import OverviewSpike from "./spike/OverviewSpike";

const container = document.getElementById("root");
if (!container) throw new Error("#root element missing from index.html");
const root = createRoot(container);
const render = (page: ReactNode) => root.render(<StrictMode>{page}</StrictMode>);

// The component demo is dev only. In production builds `import.meta.env.DEV` is the constant false, so this
// branch and its dynamic import are removed and the demo is never bundled. React Router replaces this in P6.2.
if (import.meta.env.DEV && location.pathname === "/dev/components") {
  void import("./dev/ComponentsDemo").then(({ default: ComponentsDemo }) => render(<ComponentsDemo />));
} else {
  render(<OverviewSpike />);
}
